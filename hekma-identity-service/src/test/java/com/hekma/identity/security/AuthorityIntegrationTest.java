package com.hekma.identity.security;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.StaffInvitationEntity;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserAuthorityEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.repository.AuthzAuditLogRepository;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.StaffInvitationRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserAuthorityRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.service.AuditService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;

import static com.hekma.identity.support.TestAuthentication.bearer;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * RBAC Phase 3 end-to-end checks through the real security filter chain: per-user authorities, grant ≤ own,
 * staff invitations, user management by tenant users, /me, patient invitation expiry and audit entries.
 */
@SpringBootTest
@Transactional
class AuthorityIntegrationTest {

    @Autowired
    private WebApplicationContext context;
    @Autowired
    private UserRepository userRepository;
    @Autowired
    private TenantRepository tenantRepository;
    @Autowired
    private UserAuthorityRepository userAuthorityRepository;
    @Autowired
    private StaffInvitationRepository invitationRepository;
    @Autowired
    private PatientDetailRepository patientDetailRepository;
    @Autowired
    private AuthzAuditLogRepository auditLogRepository;

    @MockitoBean
    private NotificationServiceClient notificationServiceClient;

    private MockMvc mockMvc;
    private String run;

    private TenantEntity root;
    private TenantEntity child;
    private TenantEntity unrelated;
    private UserEntity owner;
    private UserEntity limited;
    private UserEntity reader;
    private UserEntity childUser;
    private UserEntity unrelatedUser;
    private UserEntity patient;
    private UserEntity admin;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();
        run = UUID.randomUUID().toString().substring(0, 8);

        root = saveTenant("root", TenantType.SPONSOR, null);
        child = saveTenant("child", TenantType.SITE, root);
        unrelated = saveTenant("unrelated", TenantType.SITE, null);

        owner = saveUser("owner", Role.SPONSOR, root, Authority.OWNER_BUNDLE);
        limited = saveUser("limited", Role.SPONSOR, root,
                EnumSet.of(Authority.AUTHORITY_ASSIGN, Authority.TENANT_READ, Authority.USER_READ));
        reader = saveUser("reader", Role.SPONSOR, root, EnumSet.of(Authority.PATIENT_READ, Authority.TENANT_READ));
        childUser = saveUser("child-user", Role.SITE, child, EnumSet.of(Authority.TENANT_READ));
        unrelatedUser = saveUser("unrelated-user", Role.SITE, unrelated, Authority.OWNER_BUNDLE);
        patient = saveUser("patient", Role.PATIENT, child, Set.of());
        admin = saveUser("admin", Role.ADMIN, null, Set.of());
        savePatientDetail(patient);
    }

    // ---------------------------------------------------------------- /me

    @Test
    @DisplayName("/me returns role, tenant path and effective authorities")
    void me_returnsAuthorities() throws Exception {
        mockMvc.perform(get("/api/v1/me").header("Authorization", bearer(reader)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("SPONSOR"))
                .andExpect(jsonPath("$.tenantPath").value(root.getPath()))
                .andExpect(jsonPath("$.authorities", containsInAnyOrder("patient:read", "tenant:read")));

        mockMvc.perform(get("/api/v1/me/authorities").header("Authorization", bearer(admin)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.authorities", hasSize(Authority.values().length)));

        mockMvc.perform(get("/api/v1/me/authorities").header("Authorization", bearer(patient)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.authorities", hasSize(0)));
    }

    // ---------------------------------------------------------------- enforcement

    @Test
    @DisplayName("Endpoints require the matching authority")
    void endpointsRequireAuthorities() throws Exception {
        mockMvc.perform(get("/api/v1/patients").header("Authorization", bearer(childUser)))
                .andExpect(status().isForbidden());
        mockMvc.perform(get("/api/v1/patients").header("Authorization", bearer(reader)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/v1/tenants/{id}/sub-tenants", root.getId())
                        .header("Authorization", bearer(reader))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lab\",\"slug\":\"lab-%s\",\"tenantType\":\"SITE\"}".formatted(run)))
                .andExpect(status().isForbidden());
        mockMvc.perform(patch("/api/v1/users/{id}/status", patient.getId())
                        .header("Authorization", bearer(reader))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isActive\":false}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("A revoked authority stops working on the very next request")
    void revocation_appliesImmediately() throws Exception {
        mockMvc.perform(get("/api/v1/patients").header("Authorization", bearer(reader))).andExpect(status().isOk());

        mockMvc.perform(put("/api/v1/users/{id}/authorities", reader.getId())
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"authorities\":[\"tenant:read\"],\"reason\":\"role change\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.authorities", containsInAnyOrder("tenant:read")));

        mockMvc.perform(get("/api/v1/patients").header("Authorization", bearer(reader))).andExpect(status().isForbidden());
        assertThat(auditLogRepository.findByTargetIdOrderByOccurredAtDesc(reader.getId()))
                .anyMatch(e -> e.getAction().equals(AuditService.AUTHORITIES_CHANGED)
                        && "patient:read,tenant:read".equals(e.getBeforeValue())
                        && "tenant:read".equals(e.getAfterValue())
                        && owner.getId().equals(e.getActorId()));
    }

    @Test
    @DisplayName("Grant ≤ own: a user cannot grant or revoke an authority it does not hold")
    void grantNotBeyondOwn() throws Exception {
        // limited holds authority:assign, tenant:read, user:read — not patient:read
        mockMvc.perform(put("/api/v1/users/{id}/authorities", reader.getId())
                        .header("Authorization", bearer(limited))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"authorities\":[\"tenant:read\"]}"))
                .andExpect(status().isForbidden());

        mockMvc.perform(put("/api/v1/users/{id}/authorities", reader.getId())
                        .header("Authorization", bearer(limited))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"authorities\":[\"patient:read\",\"tenant:read\",\"user:read\"]}"))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("Authorities: no self-change, no out-of-subtree targets, unknown keys rejected")
    void authorityChangeGuards() throws Exception {
        mockMvc.perform(put("/api/v1/users/{id}/authorities", owner.getId())
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"authorities\":[]}"))
                .andExpect(status().isForbidden());
        mockMvc.perform(put("/api/v1/users/{id}/authorities", unrelatedUser.getId())
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"authorities\":[]}"))
                .andExpect(status().isNotFound());
        mockMvc.perform(put("/api/v1/users/{id}/authorities", reader.getId())
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"authorities\":[\"everything:all\"]}"))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get("/api/v1/users/{id}/authorities", childUser.getId()).header("Authorization", bearer(limited)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.authorities", containsInAnyOrder("tenant:read")));
    }

    // ---------------------------------------------------------------- users

    @Test
    @DisplayName("A tenant user with user:manage manages users in its subtree only, never itself")
    void userManagementByTenantUsers() throws Exception {
        mockMvc.perform(patch("/api/v1/users/{id}/status", childUser.getId())
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isActive\":false,\"reason\":\"left the site\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isActive").value(false));
        mockMvc.perform(patch("/api/v1/users/{id}/status", unrelatedUser.getId())
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isActive\":false}"))
                .andExpect(status().isNotFound());
        mockMvc.perform(patch("/api/v1/users/{id}/status", admin.getId())
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isActive\":false}"))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("User listing is scoped to the caller's subtree")
    void listUsers_scoped() throws Exception {
        mockMvc.perform(get("/api/v1/users").param("size", "50").header("Authorization", bearer(limited)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[*].email", hasItem(childUser.getEmail())))
                .andExpect(jsonPath("$.content[?(@.email == '%s')]".formatted(unrelatedUser.getEmail()), hasSize(0)));
        mockMvc.perform(get("/api/v1/users").header("Authorization", bearer(reader)))
                .andExpect(status().isForbidden());
    }

    // ---------------------------------------------------------------- staff invitations

    @Test
    @DisplayName("Staff invitation: role follows the tenant type, default authorities, single use")
    void staffInvitation_fullFlow() throws Exception {
        String email = "invitee-" + run + "@hekma.test";
        mockMvc.perform(post("/api/v1/users/invite")
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"%s\",\"tenantId\":\"%s\"}".formatted(email, child.getId())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.role").value("SITE"))
                .andExpect(jsonPath("$.authorities", containsInAnyOrder("patient:create", "patient:read", "tenant:read")));

        ArgumentCaptor<String> link = ArgumentCaptor.forClass(String.class);
        verify(notificationServiceClient).sendStaffInvitationEmail(eq(email), any(), anyString(), link.capture(), any());
        String token = link.getValue().substring(link.getValue().indexOf("token=") + 6);

        String accept = "{\"token\":\"%s\",\"password\":\"InviteePassword123!\",\"displayName\":\"Invitee\"}".formatted(token);
        mockMvc.perform(post("/api/v1/users/accept-invite").contentType(MediaType.APPLICATION_JSON).content(accept))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.role").value("SITE"))
                .andExpect(jsonPath("$.tenantId").value(child.getId().toString()));

        UserEntity invitee = userRepository.findByEmail(email).orElseThrow();
        assertThat(userAuthorityRepository.findAuthoritiesByUserId(invitee.getId()))
                .containsExactlyInAnyOrder(Authority.TENANT_READ, Authority.PATIENT_READ, Authority.PATIENT_CREATE);

        mockMvc.perform(post("/api/v1/users/accept-invite").contentType(MediaType.APPLICATION_JSON).content(accept))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("Staff invitation: authorities beyond the inviter's are refused; other trees and expired tokens fail")
    void staffInvitation_guards() throws Exception {
        mockMvc.perform(post("/api/v1/users/invite")
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"x-%s@hekma.test\",\"tenantId\":\"%s\"}".formatted(run, unrelated.getId())))
                .andExpect(status().isNotFound());

        UserEntity inviter = saveUser("inviter", Role.SPONSOR, root, EnumSet.of(Authority.USER_INVITE, Authority.TENANT_READ));
        mockMvc.perform(post("/api/v1/users/invite")
                        .header("Authorization", bearer(inviter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"y-%s@hekma.test\",\"tenantId\":\"%s\",\"authorities\":[\"user:manage\"]}".formatted(run, root.getId())))
                .andExpect(status().isForbidden());

        // Default bundle is capped by the inviter's own authorities.
        mockMvc.perform(post("/api/v1/users/invite")
                        .header("Authorization", bearer(inviter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"z-%s@hekma.test\",\"tenantId\":\"%s\"}".formatted(run, root.getId())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.authorities", containsInAnyOrder("tenant:read")));

        ArgumentCaptor<String> link = ArgumentCaptor.forClass(String.class);
        verify(notificationServiceClient).sendStaffInvitationEmail(eq("z-" + run + "@hekma.test"), any(), anyString(), link.capture(), any());
        String token = link.getValue().substring(link.getValue().indexOf("token=") + 6);
        StaffInvitationEntity invitation = invitationRepository.findAll().stream()
                .filter(i -> i.getEmail().equals("z-" + run + "@hekma.test")).findFirst().orElseThrow();
        invitation.setExpiresAt(Instant.now().minus(1, ChronoUnit.MINUTES));
        invitationRepository.save(invitation);

        mockMvc.perform(post("/api/v1/users/accept-invite").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"%s\",\"password\":\"InviteePassword123!\"}".formatted(token)))
                .andExpect(status().isBadRequest());
    }

    // ---------------------------------------------------------------- patients

    @Test
    @DisplayName("Expired patient invitations cannot be accepted")
    void patientInvitation_expired() throws Exception {
        UserEntity staged = userRepository.save(UserEntity.builder()
                .firebaseUid("pending-invite-" + run).email("staged-" + run + "@hekma.test").role(Role.PATIENT)
                .status(UserStatus.PENDING_VERIFICATION).isActive(false).tenant(child).build());
        patientDetailRepository.save(PatientDetailEntity.builder()
                .user(staged).firstName("S").lastName("P").invitationCode("INV-" + run)
                .invitationExpiresAt(Instant.now().minus(1, ChronoUnit.HOURS)).consentedAt(Instant.now()).build());

        mockMvc.perform(post("/api/v1/patients/accept-invite").contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"invitationToken":"INV-%s","password":"PatientPassword123!","termsAccepted":true,
                                 "privacyPolicyAccepted":true,"healthDataConsentAccepted":true}
                                """.formatted(run)))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("A patient can update its own profile but not another patient's")
    void patientUpdate_selfOnly() throws Exception {
        mockMvc.perform(patch("/api/v1/patients/{id}", patient.getId())
                        .header("Authorization", bearer(patient))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"firstName\":\"Alicia\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.firstName").value("Alicia"));

        UserEntity other = saveUser("other-patient", Role.PATIENT, child, Set.of());
        savePatientDetail(other);
        mockMvc.perform(patch("/api/v1/patients/{id}", other.getId())
                        .header("Authorization", bearer(patient))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"firstName\":\"Mallory\"}"))
                .andExpect(status().isNotFound());
    }

    // ---------------------------------------------------------------- helpers

    private TenantEntity saveTenant(String name, TenantType type, TenantEntity parent) {
        return tenantRepository.save(TenantEntity.builder()
                .name(name + " " + run).slug(name + "-" + run).tenantType(type)
                .status(TenantStatus.ACTIVE).parent(parent).build());
    }

    private UserEntity saveUser(String name, Role role, TenantEntity tenant, Set<Authority> authorities) {
        UserEntity user = userRepository.save(UserEntity.builder()
                .firebaseUid("fb-" + name + "-" + run)
                .email(name + "-" + run + "@hekma.test")
                .authEmail(name + "-" + run + "@hekma.test")
                .role(role)
                .displayName(name)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .tenant(tenant)
                .build());
        authorities.forEach(a -> userAuthorityRepository.save(UserAuthorityEntity.builder().user(user).authority(a).build()));
        return user;
    }

    private void savePatientDetail(UserEntity user) {
        patientDetailRepository.save(PatientDetailEntity.builder()
                .user(user).firstName("Test").lastName(user.getDisplayName())
                .termsAccepted(true).privacyPolicyAccepted(true).healthDataConsentAccepted(true)
                .consentedAt(Instant.now()).build());
    }
}
