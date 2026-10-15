package com.hekma.identity.security;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.OtpRequestEntity;
import com.hekma.identity.domain.otp.OtpStatus;
import com.hekma.identity.repository.OtpRequestRepository;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserRepository;
import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.time.Instant;
import java.util.UUID;

import static com.hekma.identity.support.TestAuthentication.bearer;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * RBAC Phase 2 end-to-end checks through the real security filter chain: tenant self-registration and activation,
 * sub-tenants, subtree visibility, suspension cascade and patient scoping across the hierarchy.
 */
@SpringBootTest
@Transactional
class TenantHierarchyIntegrationTest {

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
    private OtpRequestRepository otpRequestRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    private MockMvc mockMvc;
    private String run;

    // Tree: root (SPONSOR) -> child (SITE) -> grandchild (SITE); root -> sibling (SITE); plus an unrelated tenant.
    private TenantEntity root;
    private TenantEntity child;
    private TenantEntity grandchild;
    private TenantEntity sibling;
    private TenantEntity unrelated;
    private UserEntity rootUser;
    private UserEntity childUser;
    private UserEntity grandchildUser;
    private UserEntity siblingUser;
    private UserEntity admin;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();

        run = UUID.randomUUID().toString().substring(0, 8);
        root = saveTenant("root", TenantType.SPONSOR, null);
        child = saveTenant("child", TenantType.SITE, root);
        grandchild = saveTenant("grandchild", TenantType.SITE, child);
        sibling = saveTenant("sibling", TenantType.SITE, root);
        unrelated = saveTenant("unrelated", TenantType.SPONSOR, null);

        rootUser = saveUser("root-user", Role.SPONSOR, root);
        childUser = saveUser("child-user", Role.SITE, child);
        grandchildUser = saveUser("grandchild-user", Role.SITE, grandchild);
        siblingUser = saveUser("sibling-user", Role.SITE, sibling);
        admin = saveUser("admin", Role.ADMIN, null);
    }

    // ---------------------------------------------------------------- tree shape

    @Test
    @DisplayName("Materialized paths and depths are computed from the parent")
    void pathsAndDepths() {
        assertThat(root.getDepth()).isZero();
        assertThat(grandchild.getDepth()).isEqualTo(2);
        assertThat(grandchild.getPath()).isEqualTo(root.getPath() + child.getId() + "/" + grandchild.getId() + "/");
        assertThat(root.containsInSubtree(grandchild)).isTrue();
        assertThat(child.containsInSubtree(sibling)).isFalse();
    }

    // ---------------------------------------------------------------- tenant self-registration

    @Test
    @DisplayName("A tenant registers itself; OTP verification activates the tenant and its owner")
    void registerTenant_thenVerifyOtp_activatesTenantAndOwner() throws Exception {
        String phone = "+1555" + (1000000 + (int) (Math.random() * 8999999));
        String body = mockMvc.perform(post("/api/v1/auth/register-tenant")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"tenantName":"Acme Trials","tenantSlug":"acme-%s","tenantType":"SITE",
                                 "phoneNumber":"%s","password":"OwnerPassword123!","displayName":"Acme Owner","verificationMode":"PHONE"}
                                """.formatted(run, phone)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tenantStatus").value("PENDING_VERIFICATION"))
                .andExpect(jsonPath("$.role").value("SITE"))
                .andExpect(jsonPath("$.status").value("PENDING_VERIFICATION"))
                .andReturn().getResponse().getContentAsString();

        UUID tenantId = UUID.fromString(JsonPath.read(body, "$.tenantId"));
        UUID userId = UUID.fromString(JsonPath.read(body, "$.userId"));
        assertThat(tenantRepository.findById(tenantId).orElseThrow().getParent()).isNull();

        // The OTP is only stored hashed; replace it with a known code for the test.
        OtpRequestEntity attempt = otpRequestRepository.findTopByPhoneNumberAndStatusOrderByCreatedAtDesc(phone, OtpStatus.PENDING).orElseThrow();
        attempt.setHashedOtp(passwordEncoder.encode("246810"));
        otpRequestRepository.save(attempt);

        mockMvc.perform(post("/api/v1/auth/otp/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attemptId\":\"%s\",\"phoneNumber\":\"%s\",\"otpCode\":\"246810\"}".formatted(attempt.getId(), phone)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.idToken").exists());

        assertThat(tenantRepository.findById(tenantId).orElseThrow().getStatus()).isEqualTo(TenantStatus.ACTIVE);
        assertThat(userRepository.findById(userId).orElseThrow().getStatus()).isEqualTo(UserStatus.ACTIVE);
    }

    @Test
    @DisplayName("Tenant registration rejects a taken slug and the GENERAL type")
    void registerTenant_invalid_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/auth/register-tenant")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"tenantName":"Dup","tenantSlug":"%s","tenantType":"SITE","email":"dup-%s@hekma.test","password":"OwnerPassword123!","verificationMode":"EMAIL"}
                                """.formatted(root.getSlug(), run)))
                .andExpect(status().isBadRequest());

        mockMvc.perform(post("/api/v1/auth/register-tenant")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"tenantName":"Gen","tenantSlug":"gen-%s","tenantType":"GENERAL","email":"gen-%s@hekma.test","password":"OwnerPassword123!","verificationMode":"EMAIL"}
                                """.formatted(run, run)))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("Admin-side top-level tenant creation no longer exists")
    void adminCreateTopLevelTenant_isGone() throws Exception {
        mockMvc.perform(post("/api/v1/tenants")
                        .header("Authorization", bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"X\",\"slug\":\"x-%s\",\"tenantType\":\"SITE\"}".formatted(run)))
                .andExpect(result -> assertThat(result.getResponse().getStatus()).isIn(404, 405));
    }

    // ---------------------------------------------------------------- sub-tenants

    @Test
    @DisplayName("A tenant user creates a sub-tenant with an owner whose role matches the sub-tenant type")
    void createSubTenant_withOwner() throws Exception {
        String body = mockMvc.perform(post("/api/v1/tenants/{id}/sub-tenants", child.getId())
                        .header("Authorization", bearer(childUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"Lab","slug":"lab-%s","tenantType":"SPONSOR",
                                 "owner":{"email":"lab-owner-%s@hekma.test","temporaryPassword":"TempPassword123!"}}
                                """.formatted(run, run)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.parentTenantId").value(child.getId().toString()))
                .andExpect(jsonPath("$.depth").value(2))
                .andReturn().getResponse().getContentAsString();

        UUID labId = UUID.fromString(JsonPath.read(body, "$.id"));
        UserEntity owner = userRepository.findByEmail("lab-owner-" + run + "@hekma.test").orElseThrow();
        assertThat(owner.getRole()).isEqualTo(Role.SPONSOR);
        assertThat(owner.getTenantId()).isEqualTo(labId);
    }

    @Test
    @DisplayName("A tenant user cannot create a sub-tenant under its parent or a sibling (404)")
    void createSubTenant_outsideSubtree_returns404() throws Exception {
        for (UUID target : new UUID[]{root.getId(), sibling.getId()}) {
            mockMvc.perform(post("/api/v1/tenants/{id}/sub-tenants", target)
                            .header("Authorization", bearer(childUser))
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"name\":\"Xy\",\"slug\":\"x-%s\",\"tenantType\":\"SITE\"}".formatted(UUID.randomUUID().toString().substring(0, 8))))
                    .andExpect(status().isNotFound());
        }
    }

    // ---------------------------------------------------------------- visibility

    @Test
    @DisplayName("Tenant listing returns the caller's own tenant and all descendants only")
    void listTenants_subtreeOnly() throws Exception {
        mockMvc.perform(get("/api/v1/tenants").param("size", "50").header("Authorization", bearer(rootUser)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[*].slug", containsInAnyOrder(
                        root.getSlug(), child.getSlug(), grandchild.getSlug(), sibling.getSlug())));

        mockMvc.perform(get("/api/v1/tenants").param("size", "50").header("Authorization", bearer(childUser)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[*].slug", containsInAnyOrder(child.getSlug(), grandchild.getSlug())));

        mockMvc.perform(get("/api/v1/tenants").param("size", "100").header("Authorization", bearer(admin)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[*].slug", hasItems(
                        root.getSlug(), child.getSlug(), grandchild.getSlug(), sibling.getSlug(), unrelated.getSlug())));

        mockMvc.perform(get("/api/v1/tenants").param("type", "SITE").header("Authorization", bearer(admin)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[*].slug", hasItems(
                        child.getSlug(), grandchild.getSlug(), sibling.getSlug())));
    }

    @Test
    @DisplayName("Ancestors can read descendants; descendants cannot read ancestors or siblings")
    void getTenant_directionality() throws Exception {
        mockMvc.perform(get("/api/v1/tenants/{id}", grandchild.getId()).header("Authorization", bearer(rootUser)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/v1/tenants/{id}", root.getId()).header("Authorization", bearer(childUser)))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/v1/tenants/{id}", sibling.getId()).header("Authorization", bearer(childUser)))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/v1/tenants/{id}/children", root.getId()).header("Authorization", bearer(rootUser)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)));
    }

    @Test
    @DisplayName("Patients of a descendant tenant are visible to ancestors, not to siblings")
    void patients_visibleUpTheTree() throws Exception {
        UserEntity patient = saveUser("patient", Role.PATIENT, grandchild);
        savePatientDetail(patient, grandchildUser);

        mockMvc.perform(get("/api/v1/patients/{id}", patient.getId()).header("Authorization", bearer(rootUser)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/v1/patients/{id}", patient.getId()).header("Authorization", bearer(childUser)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/v1/patients/{id}", patient.getId()).header("Authorization", bearer(siblingUser)))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/v1/patients").header("Authorization", bearer(rootUser)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(1)));
        mockMvc.perform(get("/api/v1/users/{id}", grandchildUser.getId()).header("Authorization", bearer(rootUser)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/v1/users/{id}", rootUser.getId()).header("Authorization", bearer(grandchildUser)))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("A patient can be invited into a sub-tenant and assigned to its user; other trees are rejected")
    void invitePatient_intoSubTenant() throws Exception {
        mockMvc.perform(post("/api/v1/patients/invite")
                        .header("Authorization", bearer(rootUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"firstName":"Jane","lastName":"Doe","email":"jane-%s@hekma.test","tenantId":"%s","assignedUserId":"%s"}
                                """.formatted(run, grandchild.getId(), grandchildUser.getId())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tenantId").value(grandchild.getId().toString()))
                .andExpect(jsonPath("$.assignedUserId").value(grandchildUser.getId().toString()));

        mockMvc.perform(post("/api/v1/patients/invite")
                        .header("Authorization", bearer(rootUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"firstName":"Jim","lastName":"Doe","email":"jim-%s@hekma.test","tenantId":"%s"}
                                """.formatted(run, unrelated.getId())))
                .andExpect(status().isNotFound());

        // An assignee in a sibling branch could not see the patient.
        mockMvc.perform(post("/api/v1/patients/invite")
                        .header("Authorization", bearer(rootUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"firstName":"Joe","lastName":"Doe","email":"joe-%s@hekma.test","tenantId":"%s","assignedUserId":"%s"}
                                """.formatted(run, grandchild.getId(), siblingUser.getId())))
                .andExpect(status().isBadRequest());
    }

    // ---------------------------------------------------------------- suspension cascade

    @Test
    @DisplayName("Suspending a tenant blocks its whole subtree; users cannot suspend their own tenant")
    void suspension_cascadesToDescendants() throws Exception {
        mockMvc.perform(patch("/api/v1/tenants/{id}/status", child.getId())
                        .header("Authorization", bearer(childUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"SUSPENDED\"}"))
                .andExpect(status().isForbidden());

        mockMvc.perform(patch("/api/v1/tenants/{id}/status", child.getId())
                        .header("Authorization", bearer(rootUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"SUSPENDED\",\"reason\":\"audit\"}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/v1/tenants/{id}", child.getId()).header("Authorization", bearer(childUser)))
                .andExpect(status().isForbidden());
        mockMvc.perform(get("/api/v1/tenants/{id}", grandchild.getId()).header("Authorization", bearer(grandchildUser)))
                .andExpect(status().isForbidden());
        mockMvc.perform(get("/api/v1/tenants/{id}", sibling.getId()).header("Authorization", bearer(siblingUser)))
                .andExpect(status().isOk());
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

    private TenantEntity saveTenant(String name, TenantType type, TenantEntity parent) {
        return tenantRepository.save(TenantEntity.builder()
                .name(name + " " + run)
                .slug(name + "-" + run)
                .tenantType(type)
                .status(TenantStatus.ACTIVE)
                .parent(parent)
                .build());
    }

    private UserEntity saveUser(String name, Role role, TenantEntity tenant) {
        return grantOwnerBundle(saveUserWithoutAuthorities(name, role, tenant));
    }

    private UserEntity saveUserWithoutAuthorities(String name, Role role, TenantEntity tenant) {
        return userRepository.save(UserEntity.builder()
                .firebaseUid("fb-" + name + "-" + run)
                .email(name + "-" + run + "@hekma.test")
                .authEmail(name + "-" + run + "@hekma.test")
                .role(role)
                .displayName(name)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .tenant(tenant)
                .build());
    }

    private void savePatientDetail(UserEntity user, UserEntity assignee) {
        patientDetailRepository.save(PatientDetailEntity.builder()
                .user(user)
                .firstName("Test")
                .lastName(user.getDisplayName())
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .consentedAt(Instant.now())
                .assignedUser(assignee)
                .build());
    }
}
