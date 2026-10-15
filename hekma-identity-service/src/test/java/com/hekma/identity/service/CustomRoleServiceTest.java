package com.hekma.identity.service;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.CustomRoleAuthorityEntity;
import com.hekma.identity.domain.CustomRoleEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.dto.role.AssignCustomRolesRequest;
import com.hekma.identity.dto.role.CreateCustomRoleRequest;
import com.hekma.identity.dto.role.CustomRoleResponse;
import com.hekma.identity.dto.role.UpdateCustomRoleRequest;
import com.hekma.identity.dto.role.UserCustomRolesResponse;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.repository.CustomRoleAuthorityRepository;
import com.hekma.identity.repository.CustomRoleRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserCustomRoleRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.EnumSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CustomRoleServiceTest {

    @Mock
    private CustomRoleRepository customRoleRepository;

    @Mock
    private CustomRoleAuthorityRepository customRoleAuthorityRepository;

    @Mock
    private UserCustomRoleRepository userCustomRoleRepository;

    @Mock
    private TenantRepository tenantRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private AuditService auditService;

    @InjectMocks
    private CustomRoleService customRoleService;

    private HekmaPrincipal adminCaller;
    private HekmaPrincipal sponsorCaller;
    private TenantEntity sponsorTenant;
    private UUID sponsorTenantId;

    @BeforeEach
    void setUp() {
        sponsorTenantId = UUID.randomUUID();
        sponsorTenant = TenantEntity.builder()
                .id(sponsorTenantId)
                .name("Pfizer Clinical")
                .path("/1/")
                .build();

        adminCaller = new HekmaPrincipal(UUID.randomUUID(), "fb-admin", "admin@hekma.com", Role.ADMIN, null, null);
        sponsorCaller = new HekmaPrincipal(
                UUID.randomUUID(),
                "fb-sponsor",
                "sponsor@pfizer.com",
                Role.SPONSOR,
                sponsorTenantId,
                "/1/",
                Set.of(Authority.ROLE_READ, Authority.ROLE_CREATE, Authority.ROLE_UPDATE, Authority.ROLE_DELETE, Authority.ROLE_ASSIGN, Authority.PATIENT_READ)
        );
    }

    @Test
    @DisplayName("Platform admin can create global custom role")
    void createCustomRole_platformAdmin_global() {
        CreateCustomRoleRequest request = CreateCustomRoleRequest.builder()
                .name("Global Monitor")
                .code("GLOBAL_MONITOR")
                .description("Monitors all trials globally")
                .authorities(Set.of("patient:read", "role:read"))
                .build();

        CustomRoleEntity savedEntity = CustomRoleEntity.builder()
                .id(UUID.randomUUID())
                .name("Global Monitor")
                .code("GLOBAL_MONITOR")
                .isSystem(false)
                .isActive(true)
                .build();

        when(customRoleRepository.existsByTenantIsNullAndCodeIgnoreCaseAndIsDeletedFalse("GLOBAL_MONITOR")).thenReturn(false);
        when(customRoleRepository.save(any(CustomRoleEntity.class))).thenReturn(savedEntity);
        when(customRoleAuthorityRepository.findAuthoritiesByCustomRoleId(savedEntity.getId())).thenReturn(Set.of(Authority.PATIENT_READ, Authority.ROLE_READ));

        CustomRoleResponse response = customRoleService.createCustomRole(request, adminCaller);

        assertThat(response).isNotNull();
        assertThat(response.getCode()).isEqualTo("GLOBAL_MONITOR");
        assertThat(response.getAuthorities()).containsExactlyInAnyOrder("patient:read", "role:read");
        verify(customRoleRepository).save(any(CustomRoleEntity.class));
    }

    @Test
    @DisplayName("Tenant staff can create custom role within their own tenant")
    void createCustomRole_tenantStaff_success() {
        CreateCustomRoleRequest request = CreateCustomRoleRequest.builder()
                .name("Site Coordinator")
                .code("SITE_COORD")
                .tenantId(sponsorTenantId)
                .authorities(Set.of("patient:read"))
                .build();

        CustomRoleEntity savedEntity = CustomRoleEntity.builder()
                .id(UUID.randomUUID())
                .tenant(sponsorTenant)
                .tenantPath("/1/")
                .name("Site Coordinator")
                .code("SITE_COORD")
                .isSystem(false)
                .isActive(true)
                .build();

        when(tenantRepository.findById(sponsorTenantId)).thenReturn(Optional.of(sponsorTenant));
        when(customRoleRepository.existsByTenant_IdAndCodeIgnoreCaseAndIsDeletedFalse(sponsorTenantId, "SITE_COORD")).thenReturn(false);
        when(customRoleRepository.save(any(CustomRoleEntity.class))).thenReturn(savedEntity);
        when(customRoleAuthorityRepository.findAuthoritiesByCustomRoleId(savedEntity.getId())).thenReturn(Set.of(Authority.PATIENT_READ));

        CustomRoleResponse response = customRoleService.createCustomRole(request, sponsorCaller);

        assertThat(response).isNotNull();
        assertThat(response.getCode()).isEqualTo("SITE_COORD");
        verify(customRoleRepository).save(any(CustomRoleEntity.class));
    }

    @Test
    @DisplayName("Tenant staff cannot bundle authorities they do not hold (Grant <= Own)")
    void createCustomRole_unheldAuthority_fails() {
        CreateCustomRoleRequest request = CreateCustomRoleRequest.builder()
                .name("Elevated Role")
                .code("ELEVATED")
                .tenantId(sponsorTenantId)
                .authorities(Set.of("tenant:update")) // caller does not hold tenant:update
                .build();

        when(tenantRepository.findById(sponsorTenantId)).thenReturn(Optional.of(sponsorTenant));
        when(customRoleRepository.existsByTenant_IdAndCodeIgnoreCaseAndIsDeletedFalse(sponsorTenantId, "ELEVATED")).thenReturn(false);

        assertThatThrownBy(() -> customRoleService.createCustomRole(request, sponsorCaller))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("Cannot bundle or assign authorities you do not hold");
    }

    @Test
    @DisplayName("Cannot modify immutable system role")
    void updateCustomRole_systemRole_fails() {
        UUID roleId = UUID.randomUUID();
        CustomRoleEntity systemRole = CustomRoleEntity.builder()
                .id(roleId)
                .name("System Admin Role")
                .code("SYS_ADMIN")
                .isSystem(true)
                .build();

        when(customRoleRepository.findByIdAndIsDeletedFalse(roleId)).thenReturn(Optional.of(systemRole));

        UpdateCustomRoleRequest request = UpdateCustomRoleRequest.builder()
                .name("New Name")
                .build();

        assertThatThrownBy(() -> customRoleService.updateCustomRole(roleId, request, adminCaller))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("System roles cannot be modified");
    }

    @Test
    @DisplayName("Cannot delete custom role if assigned to active users")
    void deleteCustomRole_activeUsers_fails() {
        UUID roleId = UUID.randomUUID();
        CustomRoleEntity role = CustomRoleEntity.builder()
                .id(roleId)
                .name("Active Role")
                .code("ACTIVE_ROLE")
                .isSystem(false)
                .build();

        when(customRoleRepository.findByIdAndIsDeletedFalse(roleId)).thenReturn(Optional.of(role));
        when(userCustomRoleRepository.countActiveUsersByCustomRoleId(roleId)).thenReturn(3L);

        assertThatThrownBy(() -> customRoleService.deleteCustomRole(roleId, adminCaller))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("currently assigned to 3 active user(s)");
    }

    @Test
    @DisplayName("Assign custom roles to staff user rejects self-elevation")
    void assignCustomRoles_selfAssignment_fails() {
        AssignCustomRolesRequest request = AssignCustomRolesRequest.builder()
                .roleIds(Set.of(UUID.randomUUID()))
                .build();

        UserEntity callerUser = UserEntity.builder()
                .id(sponsorCaller.userId())
                .role(Role.SPONSOR)
                .tenant(sponsorTenant)
                .build();

        when(userRepository.findById(sponsorCaller.userId())).thenReturn(Optional.of(callerUser));

        assertThatThrownBy(() -> customRoleService.assignCustomRoles(sponsorCaller.userId(), request, sponsorCaller))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("cannot assign or modify custom roles for yourself");
    }

    @Test
    @DisplayName("Assign custom roles rejects roles outside target user's tenant subtree")
    void assignCustomRoles_unheldAuthority_fails() {
        UUID targetUserId = UUID.randomUUID();
        UUID roleId = UUID.randomUUID();

        UserEntity targetUser = UserEntity.builder()
                .id(targetUserId)
                .role(Role.SPONSOR)
                .tenant(sponsorTenant)
                .build();

        CustomRoleEntity role = CustomRoleEntity.builder()
                .id(roleId)
                .name("Super Privileged")
                .code("SUPER")
                .isActive(true)
                .build();

        when(userRepository.findById(targetUserId)).thenReturn(Optional.of(targetUser));
        when(customRoleRepository.findByIdAndIsDeletedFalse(roleId)).thenReturn(Optional.of(role));
        // Role has tenant:manage which sponsorCaller does not hold
        when(customRoleAuthorityRepository.findAuthoritiesByCustomRoleId(roleId)).thenReturn(Set.of(Authority.SUBTENANT_MANAGE));

        AssignCustomRolesRequest request = AssignCustomRolesRequest.builder()
                .roleIds(Set.of(roleId))
                .build();

        assertThatThrownBy(() -> customRoleService.assignCustomRoles(targetUserId, request, sponsorCaller))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("Cannot bundle or assign authorities you do not hold");
    }

    @Test
    @DisplayName("Assign custom roles succeeds when valid")
    void assignCustomRoles_success() {
        UUID targetUserId = UUID.randomUUID();
        UUID roleId = UUID.randomUUID();

        UserEntity targetUser = UserEntity.builder()
                .id(targetUserId)
                .email("nurse@pfizer.com")
                .role(Role.SPONSOR)
                .tenant(sponsorTenant)
                .build();

        CustomRoleEntity role = CustomRoleEntity.builder()
                .id(roleId)
                .name("Patient Coordinator")
                .code("PATIENT_COORD")
                .isActive(true)
                .tenant(sponsorTenant)
                .tenantPath("/1/")
                .build();

        when(userRepository.findById(targetUserId)).thenReturn(Optional.of(targetUser));
        when(customRoleRepository.findByIdAndIsDeletedFalse(roleId)).thenReturn(Optional.of(role));
        when(customRoleAuthorityRepository.findAuthoritiesByCustomRoleId(roleId)).thenReturn(Set.of(Authority.PATIENT_READ));
        when(customRoleRepository.findAuthoritiesByUserId(targetUserId)).thenReturn(Set.of(Authority.PATIENT_READ));

        AssignCustomRolesRequest request = AssignCustomRolesRequest.builder()
                .roleIds(Set.of(roleId))
                .reason("Assigning clinical duties")
                .build();

        UserCustomRolesResponse response = customRoleService.assignCustomRoles(targetUserId, request, sponsorCaller);

        assertThat(response).isNotNull();
        assertThat(response.getUserId()).isEqualTo(targetUserId);
        assertThat(response.getInheritedAuthorities()).contains("patient:read");
        verify(userCustomRoleRepository).deleteByUserId(targetUserId);
    }
}
