package com.hekma.identity.security;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.time.Instant;
import java.util.UUID;

import static com.hekma.identity.support.TestAuthentication.bearer;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * End-to-end access checks through the real security filter chain (mock Firebase tokens).
 * Covers authentication, spoofing resistance, tenant scoping and role restrictions (RBAC Phase 1).
 */
@SpringBootTest
@Transactional
class SecurityAccessIntegrationTest {

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private com.hekma.identity.repository.UserAuthorityRepository userAuthorityRepository;

    @Autowired
    private TenantRepository tenantRepository;

    @Autowired
    private PatientDetailRepository patientDetailRepository;

    @Autowired
    private FirebaseService firebaseService;

    private MockMvc mockMvc;

    private TenantEntity tenantA;
    private TenantEntity tenantB;
    private UserEntity admin;
    private UserEntity siteA;
    private UserEntity siteB;
    private UserEntity patientA;
    private UserEntity patientB;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();

        String run = UUID.randomUUID().toString().substring(0, 8);
        tenantA = tenantRepository.save(TenantEntity.builder()
                .name("Site A " + run).slug("site-a-" + run).tenantType(TenantType.SITE).status(TenantStatus.ACTIVE).build());
        tenantB = tenantRepository.save(TenantEntity.builder()
                .name("Site B " + run).slug("site-b-" + run).tenantType(TenantType.SITE).status(TenantStatus.ACTIVE).build());

        admin = saveUser("admin-" + run, Role.ADMIN, null);
        siteA = saveUser("site-a-" + run, Role.SITE, tenantA);
        siteB = saveUser("site-b-" + run, Role.SITE, tenantB);
        patientA = saveUser("patient-a-" + run, Role.PATIENT, tenantA);
        patientB = saveUser("patient-b-" + run, Role.PATIENT, tenantB);
        savePatientDetail(patientA);
        savePatientDetail(patientB);
    }

    // ---------------------------------------------------------------- authentication

    @Test
    @DisplayName("Protected REST endpoints reject anonymous requests with 401")
    void anonymous_protectedEndpoint_returns401() throws Exception {
        mockMvc.perform(get("/api/v1/users/{id}", patientA.getId()))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    @DisplayName("Anonymous callers cannot create ADMIN users")
    void anonymous_inviteAdmin_returns401() throws Exception {
        mockMvc.perform(post("/api/v1/system-admin/invite-admin")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"evil@hekma.com\",\"temporaryPassword\":\"Password123!\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("GraphQL requires authentication")
    void anonymous_graphql_returns401() throws Exception {
        mockMvc.perform(post("/graphql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"{ users { id email } }\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("Invalid bearer tokens are rejected with 401")
    void invalidToken_returns401() throws Exception {
        mockMvc.perform(get("/api/v1/users/{id}", patientA.getId())
                        .header("Authorization", "Bearer not-a-valid-token"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("Revoked sessions are rejected with 401")
    void revokedToken_returns401() throws Exception {
        String token = bearer(patientA);
        Thread.sleep(2);
        firebaseService.revokeRefreshTokens(patientA.getFirebaseUid());

        mockMvc.perform(get("/api/v1/users/{id}", patientA.getId()).header("Authorization", token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("Deactivated users are rejected with 403 even with a valid token")
    void inactiveUser_returns403() throws Exception {
        patientA.setStatus(UserStatus.INACTIVE);
        patientA.setIsActive(false);
        userRepository.save(patientA);

        mockMvc.perform(get("/api/v1/users/{id}", patientA.getId()).header("Authorization", bearer(patientA)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("Users of a suspended tenant are rejected with 403")
    void suspendedTenantUser_returns403() throws Exception {
        tenantA.setStatus(TenantStatus.SUSPENDED);
        tenantRepository.save(tenantA);

        mockMvc.perform(get("/api/v1/users/{id}", siteA.getId()).header("Authorization", bearer(siteA)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("Public registration endpoint is reachable without a token but rejects non-PATIENT roles")
    void publicRegister_nonPatientRole_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"sponsor.signup@hekma.com\",\"password\":\"Password123!\",\"role\":\"SPONSOR\",\"phoneNumber\":\"+15550001111\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("Only PATIENT")));
    }

    // ---------------------------------------------------------------- role restrictions & spoofing

    @Test
    @DisplayName("Only SYSTEM_ADMIN can create ADMIN users")
    void admin_inviteAdmin_returns403() throws Exception {
        mockMvc.perform(post("/api/v1/system-admin/admins")
                        .header("Authorization", bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"another.admin@hekma.com\",\"temporaryPassword\":\"Password123!\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("X-Operator-Id cannot be used to impersonate an administrator")
    void siteUser_spoofedOperatorHeader_returns403() throws Exception {
        UserEntity plainSiteUser = saveUserWithoutAuthorities("plain-site-" + UUID.randomUUID().toString().substring(0, 8), Role.SITE, tenantA);
        mockMvc.perform(patch("/api/v1/users/{id}/status", patientA.getId())
                        .header("Authorization", bearer(plainSiteUser))
                        .header("X-Operator-Id", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isActive\":false}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("Administrators cannot deactivate their own account")
    void admin_deactivateSelf_returns403() throws Exception {
        mockMvc.perform(patch("/api/v1/users/{id}/status", admin.getId())
                        .header("Authorization", bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isActive\":false}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("ADMIN can deactivate a patient")
    void admin_deactivatePatient_returns200() throws Exception {
        mockMvc.perform(patch("/api/v1/users/{id}/status", patientA.getId())
                        .header("Authorization", bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isActive\":false}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isActive").value(false));
    }

    @Test
    @DisplayName("GraphQL is restricted to platform administrators")
    void siteUser_graphql_forbidden() throws Exception {
        mockMvc.perform(post("/graphql")
                        .header("Authorization", bearer(siteA))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"{ users { id email } }\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.users").doesNotExist())
                .andExpect(jsonPath("$.errors[0].extensions.classification").value("FORBIDDEN"));
    }

    // ---------------------------------------------------------------- scoping

    @Test
    @DisplayName("A patient can read its own profile but not another user's (404)")
    void patient_readsSelfButNotOthers() throws Exception {
        mockMvc.perform(get("/api/v1/users/{id}", patientA.getId()).header("Authorization", bearer(patientA)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/v1/users/{id}", siteA.getId()).header("Authorization", bearer(patientA)))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("A patient listing patients only sees itself")
    void patient_listPatients_onlyOwnRecord() throws Exception {
        mockMvc.perform(get("/api/v1/patients").header("Authorization", bearer(patientA)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(1)))
                .andExpect(jsonPath("$.content[0].id").value(patientA.getId().toString()));
    }

    @Test
    @DisplayName("A site user cannot read a patient of another tenant (404)")
    void siteUser_crossTenantPatient_returns404() throws Exception {
        mockMvc.perform(get("/api/v1/patients/{id}", patientA.getId()).header("Authorization", bearer(siteA)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/v1/patients/{id}", patientB.getId()).header("Authorization", bearer(siteA)))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("A site user cannot switch tenant context with X-Tenant-ID (404)")
    void siteUser_foreignTenantHeader_returns404() throws Exception {
        mockMvc.perform(get("/api/v1/patients")
                        .header("Authorization", bearer(siteA))
                        .header("X-Tenant-ID", tenantB.getId().toString()))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("A site user can read its own tenant but not another tenant (404)")
    void siteUser_readsOwnTenantOnly() throws Exception {
        mockMvc.perform(get("/api/v1/tenants/{id}", tenantA.getId()).header("Authorization", bearer(siteA)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/v1/tenants/{id}", tenantB.getId()).header("Authorization", bearer(siteA)))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("Tenant listing: site users see only their own subtree, patients are forbidden, admins see all")
    void siteUser_listTenants_returnsOwnSubtreeOnly() throws Exception {
        mockMvc.perform(get("/api/v1/tenants").header("Authorization", bearer(siteA)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(1)))
                .andExpect(jsonPath("$.content[0].id").value(tenantA.getId().toString()));

        mockMvc.perform(get("/api/v1/tenants").header("Authorization", bearer(patientA)))
                .andExpect(status().isForbidden());

        mockMvc.perform(get("/api/v1/tenants").header("Authorization", bearer(admin)))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("2FA settings of another user cannot be changed by a non-admin (404)")
    void patient_updateOtherUsersTwoFactor_returns404() throws Exception {
        mockMvc.perform(patch("/api/v1/users/{id}/2fa", patientB.getId())
                        .header("Authorization", bearer(patientA))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"twoFactorEnabled\":true}"))
                .andExpect(status().isNotFound());
    }

    // ---------------------------------------------------------------- password change

    @Test
    @DisplayName("change-password requires authentication")
    void anonymous_changePassword_returns401() throws Exception {
        mockMvc.perform(post("/api/v1/auth/change-password")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"OldPassword123!\",\"newPassword\":\"NewPassword123!\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("change-password rejects a new password that violates the policy")
    void changePassword_weakNewPassword_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/auth/change-password")
                        .header("Authorization", bearer(siteA))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"OldPassword123!\",\"newPassword\":\"weak\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("change-password validates via Firebase, revokes the old session and returns working tokens")
    void changePassword_fullFlow() throws Exception {
        String email = "pwd-" + UUID.randomUUID().toString().substring(0, 8) + "@hekma.test";
        String uid = firebaseService.createUser(email, "OldPassword123!", "Pwd User", Role.SITE).getUid();
        UserEntity user = userRepository.save(UserEntity.builder()
                .firebaseUid(uid).email(email).authEmail(email).role(Role.SITE).displayName("Pwd User")
                .status(UserStatus.ACTIVE).isActive(true).tenant(tenantA).build());
        String oldToken = bearer(user);

        mockMvc.perform(post("/api/v1/auth/change-password")
                        .header("Authorization", oldToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"WrongPassword123!\",\"newPassword\":\"NewPassword123!\"}"))
                .andExpect(status().isUnauthorized());

        Thread.sleep(2);
        String body = mockMvc.perform(post("/api/v1/auth/change-password")
                        .header("Authorization", oldToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"OldPassword123!\",\"newPassword\":\"NewPassword123!\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.idToken").exists())
                .andReturn().getResponse().getContentAsString();
        String newToken = "Bearer " + com.jayway.jsonpath.JsonPath.read(body, "$.idToken");

        mockMvc.perform(get("/api/v1/users/{id}", user.getId()).header("Authorization", oldToken))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get("/api/v1/users/{id}", user.getId()).header("Authorization", newToken))
                .andExpect(status().isOk());
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> firebaseService.signInWithPassword(email, "OldPassword123!"))
                .isInstanceOf(com.hekma.identity.exception.InvalidTokenException.class);
    }

    // ---------------------------------------------------------------- helpers

    private UserEntity grantOwnerBundle(UserEntity user) {
        if (user.getRole() == Role.SPONSOR || user.getRole() == Role.SITE) {
            for (com.hekma.identity.domain.Authority authority : com.hekma.identity.domain.Authority.OWNER_BUNDLE) {
                userAuthorityRepository.save(com.hekma.identity.domain.UserAuthorityEntity.builder()
                        .user(user).authority(authority).build());
            }
        }
        return user;
    }

    private UserEntity saveUser(String name, Role role, TenantEntity tenant) {
        return grantOwnerBundle(saveUserWithoutAuthorities(name, role, tenant));
    }

    private UserEntity saveUserWithoutAuthorities(String name, Role role, TenantEntity tenant) {
        return userRepository.save(UserEntity.builder()
                .firebaseUid("fb-" + name)
                .email(name + "@hekma.test")
                .authEmail(name + "@hekma.test")
                .role(role)
                .displayName(name)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .tenant(tenant)
                .build());
    }

    private void savePatientDetail(UserEntity user) {
        patientDetailRepository.save(PatientDetailEntity.builder()
                .user(user)
                .firstName("Test")
                .lastName(user.getDisplayName())
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .consentedAt(Instant.now())
                .assignedUser(null)
                .build());
    }
}
