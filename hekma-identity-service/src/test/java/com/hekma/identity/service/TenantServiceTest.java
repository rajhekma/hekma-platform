package com.hekma.identity.service;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.dto.tenant.SubTenantCreateRequest;
import com.hekma.identity.dto.tenant.TenantOwnerRequest;
import com.hekma.identity.dto.tenant.TenantResponse;
import com.hekma.identity.dto.tenant.TenantStatusUpdateRequest;
import com.hekma.identity.dto.tenant.TenantUpdateRequest;
import com.hekma.identity.exception.TenantNotFoundException;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseUserDto;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class TenantServiceTest {

    @Mock
    private TenantRepository tenantRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private FirebaseService firebaseService;

    @Mock
    private AuthorityService authorityService;

    @Mock
    private AuditService auditService;

    @Mock
    private RoleAuthorityService roleAuthorityService;

    @InjectMocks
    private TenantService tenantService;

    private TenantEntity defaultTenant;
    private TenantEntity sponsorTenant;
    private TenantEntity siteChild;
    private TenantEntity otherTenant;
    private HekmaPrincipal admin;
    private HekmaPrincipal sponsorUser;
    private HekmaPrincipal siteUser;

    @BeforeEach
    void setUp() {
        defaultTenant = tenant(UUID.fromString("00000000-0000-0000-0000-000000000001"), "default-tenant", TenantType.GENERAL, null);
        defaultTenant.setDefaultTenant(true);
        sponsorTenant = tenant(UUID.randomUUID(), "pfizer", TenantType.SPONSOR, null);
        siteChild = tenant(UUID.randomUUID(), "pfizer-site-boston", TenantType.SITE, sponsorTenant);
        otherTenant = tenant(UUID.randomUUID(), "novartis", TenantType.SPONSOR, null);

        admin = new HekmaPrincipal(UUID.randomUUID(), "fb-admin", "admin@hekma.com", Role.ADMIN, null, null);
        sponsorUser = staff(Role.SPONSOR, sponsorTenant);
        siteUser = staff(Role.SITE, siteChild);
    }

    private static TenantEntity tenant(UUID id, String slug, TenantType type, TenantEntity parent) {
        return TenantEntity.builder()
                .id(id)
                .name(slug)
                .slug(slug)
                .tenantType(type)
                .status(TenantStatus.ACTIVE)
                .parent(parent)
                .path((parent != null ? parent.getPath() : "/") + id + "/")
                .depth(parent != null ? parent.getDepth() + 1 : 0)
                .build();
    }

    private static HekmaPrincipal staff(Role role, TenantEntity tenant) {
        return new HekmaPrincipal(UUID.randomUUID(), "fb-" + role, role + "@hekma.com", role, tenant.getId(), tenant.getPath(),
                com.hekma.identity.domain.Authority.OWNER_BUNDLE);
    }

    private static SubTenantCreateRequest subTenantRequest(String slug, TenantType type) {
        return SubTenantCreateRequest.builder().name("Child " + slug).slug(slug).tenantType(type).build();
    }

    // ==========================================
    // createSubTenant
    // ==========================================

    @Test
    @DisplayName("A tenant user creates a sub-tenant of a different type below its own tenant")
    void createSubTenant_byStaff_success() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));
        when(tenantRepository.existsBySlug("pfizer-site-nyc")).thenReturn(false);
        when(tenantRepository.save(any(TenantEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        TenantResponse response = tenantService.createSubTenant(sponsorTenant.getId(),
                subTenantRequest("pfizer-site-nyc", TenantType.SITE), sponsorUser);

        assertThat(response.getSlug()).isEqualTo("pfizer-site-nyc");
        assertThat(response.getTenantType()).isEqualTo(TenantType.SITE);
        assertThat(response.getParentTenantId()).isEqualTo(sponsorTenant.getId());
        verify(tenantRepository).save(argThat(t -> t.getParent() == sponsorTenant && t.getStatus() == TenantStatus.ACTIVE));
    }

    @Test
    @DisplayName("A tenant user cannot create a sub-tenant outside its subtree (404)")
    void createSubTenant_outsideSubtree_throwsNotFound() {
        when(tenantRepository.findById(otherTenant.getId())).thenReturn(Optional.of(otherTenant));

        assertThatThrownBy(() -> tenantService.createSubTenant(otherTenant.getId(),
                subTenantRequest("x-site", TenantType.SITE), sponsorUser))
                .isInstanceOf(TenantNotFoundException.class);
        verify(tenantRepository, never()).save(any());
    }

    @Test
    @DisplayName("A child-tenant user cannot create a sub-tenant under its parent (404)")
    void createSubTenant_underAncestor_throwsNotFound() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));

        assertThatThrownBy(() -> tenantService.createSubTenant(sponsorTenant.getId(),
                subTenantRequest("sibling-site", TenantType.SITE), siteUser))
                .isInstanceOf(TenantNotFoundException.class);
    }

    @Test
    @DisplayName("No sub-tenants can be created under the default tenant")
    void createSubTenant_underDefaultTenant_throwsUnauthorized() {
        when(tenantRepository.findById(defaultTenant.getId())).thenReturn(Optional.of(defaultTenant));

        assertThatThrownBy(() -> tenantService.createSubTenant(defaultTenant.getId(),
                subTenantRequest("hekma-child", TenantType.SITE), admin))
                .isInstanceOf(UnauthorizedOperationException.class);
    }

    @Test
    @DisplayName("Sub-tenants must be SPONSOR or SITE")
    void createSubTenant_generalType_throwsIllegalArgument() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));

        assertThatThrownBy(() -> tenantService.createSubTenant(sponsorTenant.getId(),
                subTenantRequest("general-child", TenantType.GENERAL), admin))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("SPONSOR or SITE");
    }

    @Test
    @DisplayName("Duplicate slugs are rejected")
    void createSubTenant_duplicateSlug_throwsIllegalArgument() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));
        when(tenantRepository.existsBySlug("pfizer-site-boston")).thenReturn(true);

        assertThatThrownBy(() -> tenantService.createSubTenant(sponsorTenant.getId(),
                subTenantRequest("pfizer-site-boston", TenantType.SITE), admin))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("already exists");
    }

    @Test
    @DisplayName("A suspended ancestor blocks sub-tenant creation")
    void createSubTenant_inactiveChain_throwsTenantSuspended() {
        when(tenantRepository.findById(siteChild.getId())).thenReturn(Optional.of(siteChild));
        when(tenantRepository.existsByIdInAndStatusNot(any(), eq(TenantStatus.ACTIVE))).thenReturn(true);

        assertThatThrownBy(() -> tenantService.createSubTenant(siteChild.getId(),
                subTenantRequest("grandchild", TenantType.SITE), admin))
                .isInstanceOf(com.hekma.identity.exception.TenantSuspendedException.class);
    }

    @Test
    @DisplayName("The sub-tenant owner gets the sub-tenant's type as role and is created in Firebase")
    void createSubTenant_withOwner_createsUserWithMatchingRole() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));
        when(tenantRepository.existsBySlug("pfizer-site-nyc")).thenReturn(false);
        when(tenantRepository.save(any(TenantEntity.class))).thenAnswer(inv -> inv.getArgument(0));
        when(userRepository.existsByEmail("owner@nyc.org")).thenReturn(false);
        when(firebaseService.getUserByEmail("owner@nyc.org")).thenReturn(Optional.empty());
        when(firebaseService.createUser(eq("owner@nyc.org"), eq("TempPassword123!"), any(), eq(Role.SITE)))
                .thenReturn(FirebaseUserDto.builder().uid("fb-owner").build());

        SubTenantCreateRequest request = subTenantRequest("pfizer-site-nyc", TenantType.SITE);
        request.setOwner(TenantOwnerRequest.builder().email("Owner@NYC.org").temporaryPassword("TempPassword123!").build());

        TenantResponse response = tenantService.createSubTenant(sponsorTenant.getId(), request, sponsorUser);

        assertThat(response.getMemberCount()).isEqualTo(1L);
        verify(userRepository).save(argThat((UserEntity u) -> u.getRole() == Role.SITE
                && "fb-owner".equals(u.getFirebaseUid()) && "owner@nyc.org".equals(u.getAuthEmail())));
    }

    @Test
    @DisplayName("If the owner cannot be saved, the Firebase account is deleted again")
    void createSubTenant_ownerPersistenceFails_rollsBackFirebase() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));
        when(tenantRepository.existsBySlug("pfizer-site-nyc")).thenReturn(false);
        when(tenantRepository.save(any(TenantEntity.class))).thenAnswer(inv -> inv.getArgument(0));
        when(firebaseService.getUserByEmail(anyString())).thenReturn(Optional.empty());
        when(firebaseService.createUser(any(), any(), any(), any())).thenReturn(FirebaseUserDto.builder().uid("fb-owner").build());
        when(userRepository.save(any(UserEntity.class))).thenThrow(new RuntimeException("DB down"));

        SubTenantCreateRequest request = subTenantRequest("pfizer-site-nyc", TenantType.SITE);
        request.setOwner(TenantOwnerRequest.builder().email("owner@nyc.org").temporaryPassword("TempPassword123!").build());

        assertThatThrownBy(() -> tenantService.createSubTenant(sponsorTenant.getId(), request, sponsorUser))
                .hasMessageContaining("DB down");
        verify(firebaseService).deleteUser("fb-owner");
    }

    // ==========================================
    // list / get / children
    // ==========================================

    @Test
    @DisplayName("Platform administrators list every tenant; tenant users list only their subtree")
    void listTenants_scopedByCaller() {
        when(tenantRepository.findAll(any(Specification.class), any(Pageable.class))).thenReturn(new PageImpl<>(List.of(sponsorTenant, siteChild)));

        tenantService.listTenants(null, null, PageRequest.of(0, 20), admin);
        verify(tenantRepository).findAll(any(Specification.class), any(Pageable.class));

        tenantService.listTenants(TenantType.SITE, TenantStatus.ACTIVE, PageRequest.of(0, 20), sponsorUser);
        verify(tenantRepository, times(2)).findAll(any(Specification.class), any(Pageable.class));
    }

    @Test
    @DisplayName("Patients cannot list tenants")
    void listTenants_patient_throwsUnauthorized() {
        HekmaPrincipal patient = new HekmaPrincipal(UUID.randomUUID(), "fb-p", null, Role.PATIENT, sponsorTenant.getId(), sponsorTenant.getPath());

        assertThatThrownBy(() -> tenantService.listTenants(null, null, PageRequest.of(0, 20), patient))
                .isInstanceOf(UnauthorizedOperationException.class);
    }

    @Test
    @DisplayName("A parent-tenant user can read a descendant tenant; a child-tenant user cannot read its parent")
    void getTenantById_subtreeVisibility() {
        when(tenantRepository.findById(siteChild.getId())).thenReturn(Optional.of(siteChild));
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));

        assertThat(tenantService.getTenantById(siteChild.getId(), sponsorUser).getId()).isEqualTo(siteChild.getId());
        assertThatThrownBy(() -> tenantService.getTenantById(sponsorTenant.getId(), siteUser))
                .isInstanceOf(TenantNotFoundException.class);
    }

    @Test
    @DisplayName("A patient can read its own tenant only")
    void getTenantById_patientOwnTenant() {
        HekmaPrincipal patient = new HekmaPrincipal(UUID.randomUUID(), "fb-p", null, Role.PATIENT, siteChild.getId(), siteChild.getPath());
        when(tenantRepository.findById(siteChild.getId())).thenReturn(Optional.of(siteChild));
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));

        assertThat(tenantService.getTenantById(siteChild.getId(), patient).getId()).isEqualTo(siteChild.getId());
        assertThatThrownBy(() -> tenantService.getTenantById(sponsorTenant.getId(), patient))
                .isInstanceOf(TenantNotFoundException.class);
    }

    @Test
    @DisplayName("getTenantById throws TenantNotFoundException when not found")
    void getTenantById_notFound_throwsException() {
        UUID unknown = UUID.randomUUID();
        when(tenantRepository.findById(unknown)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> tenantService.getTenantById(unknown, admin))
                .isInstanceOf(TenantNotFoundException.class);
    }

    @Test
    @DisplayName("getChildren returns the direct sub-tenants")
    void getChildren_returnsDirectChildren() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));
        when(tenantRepository.findByParent_IdOrderByNameAsc(sponsorTenant.getId())).thenReturn(List.of(siteChild));

        List<TenantResponse> children = tenantService.getChildren(sponsorTenant.getId(), sponsorUser);

        assertThat(children).extracting(TenantResponse::getSlug).containsExactly("pfizer-site-boston");
        assertThat(children.getFirst().getDepth()).isEqualTo(1);
    }

    // ==========================================
    // status & update
    // ==========================================

    @Test
    @DisplayName("updateTenantStatus prohibits suspending or deactivating the default platform tenant")
    void updateTenantStatus_defaultTenantCannotBeSuspended() {
        when(tenantRepository.findById(defaultTenant.getId())).thenReturn(Optional.of(defaultTenant));

        TenantStatusUpdateRequest request = TenantStatusUpdateRequest.builder().status(TenantStatus.SUSPENDED).build();

        assertThatThrownBy(() -> tenantService.updateTenantStatus(defaultTenant.getId(), request, admin))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("cannot be suspended or deactivated");
    }

    @Test
    @DisplayName("A tenant user can suspend a descendant but not its own tenant")
    void updateTenantStatus_staffDescendantOnly() {
        when(tenantRepository.findById(siteChild.getId())).thenReturn(Optional.of(siteChild));
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));
        when(tenantRepository.save(any(TenantEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        TenantStatusUpdateRequest suspend = TenantStatusUpdateRequest.builder().status(TenantStatus.SUSPENDED).reason("audit").build();

        assertThat(tenantService.updateTenantStatus(siteChild.getId(), suspend, sponsorUser).getStatus())
                .isEqualTo(TenantStatus.SUSPENDED);
        assertThatThrownBy(() -> tenantService.updateTenantStatus(sponsorTenant.getId(), suspend, sponsorUser))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("own tenant");
    }

    @Test
    @DisplayName("PENDING_VERIFICATION cannot be set through the status API")
    void updateTenantStatus_pendingVerification_throwsIllegalArgument() {
        when(tenantRepository.findById(sponsorTenant.getId())).thenReturn(Optional.of(sponsorTenant));

        TenantStatusUpdateRequest request = TenantStatusUpdateRequest.builder().status(TenantStatus.PENDING_VERIFICATION).build();

        assertThatThrownBy(() -> tenantService.updateTenantStatus(sponsorTenant.getId(), request, admin))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("updateTenant updates metadata for a tenant in scope")
    void updateTenant_success() {
        when(tenantRepository.findById(siteChild.getId())).thenReturn(Optional.of(siteChild));
        when(tenantRepository.save(any(TenantEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        TenantUpdateRequest request = TenantUpdateRequest.builder().name("Boston Site").contactEmail("OPS@Boston.org").build();

        TenantResponse response = tenantService.updateTenant(siteChild.getId(), request, sponsorUser);

        assertThat(response.getName()).isEqualTo("Boston Site");
        assertThat(response.getContactEmail()).isEqualTo("ops@boston.org");
    }
}
