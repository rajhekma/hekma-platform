package com.hekma.identity.security;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.RoleAuthorityEntity;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserAuthorityEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.repository.AuthzAuditLogRepository;
import com.hekma.identity.repository.RoleAuthorityRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserAuthorityRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.service.AuditService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.util.List;
import java.util.UUID;

import static com.hekma.identity.support.TestAuthentication.bearer;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Transactional
class RoleAuthorityIntegrationTest {

    @Autowired
    private WebApplicationContext context;
    @Autowired
    private UserRepository userRepository;
    @Autowired
    private TenantRepository tenantRepository;
    @Autowired
    private UserAuthorityRepository userAuthorityRepository;
    @Autowired
    private RoleAuthorityRepository roleAuthorityRepository;
    @Autowired
    private AuthzAuditLogRepository auditLogRepository;

    @MockitoBean
    private NotificationServiceClient notificationServiceClient;

    private MockMvc mockMvc;
    private String run;

    private TenantEntity rootTenant;
    private UserEntity systemAdmin;
    private UserEntity admin;
    private UserEntity siteUser;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();
        run = UUID.randomUUID().toString().substring(0, 8);

        rootTenant = tenantRepository.save(TenantEntity.builder()
                .name("Root Tenant " + run)
                .slug("root-" + run)
                .tenantType(TenantType.SITE)
                .status(TenantStatus.ACTIVE)
                .build());

        systemAdmin = saveUser("sysadmin", Role.SYSTEM_ADMIN, null);
        admin = saveUser("admin", Role.ADMIN, null);
        siteUser = saveUser("site-user", Role.SITE, rootTenant);

        // Give initial authorities to siteUser
        userAuthorityRepository.save(UserAuthorityEntity.builder().user(siteUser).authority(Authority.TENANT_READ).build());
        userAuthorityRepository.save(UserAuthorityEntity.builder().user(siteUser).authority(Authority.PATIENT_READ).build());
    }

    @Test
    @DisplayName("GET /api/v1/authorities returns 200 with all 17 authorities for authenticated users")
    void getCatalogue_authenticated_returns12() throws Exception {
        mockMvc.perform(get("/api/v1/authorities").header("Authorization", bearer(siteUser)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(17)))
                .andExpect(jsonPath("$[0].key").isNotEmpty())
                .andExpect(jsonPath("$[0].category").isNotEmpty())
                .andExpect(jsonPath("$[0].name").isNotEmpty());
    }

    @Test
    @DisplayName("GET /api/v1/system-admin/authorities returns 200 for SYSTEM_ADMIN, 403 for ADMIN/SITE")
    void getSystemAdminAuthorities_accessControl() throws Exception {
        mockMvc.perform(get("/api/v1/system-admin/authorities").header("Authorization", bearer(systemAdmin)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(17)));

        mockMvc.perform(get("/api/v1/system-admin/authorities").header("Authorization", bearer(admin)))
                .andExpect(status().isForbidden());

        mockMvc.perform(get("/api/v1/system-admin/authorities").header("Authorization", bearer(siteUser)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("GET /api/v1/system-admin/roles/authorities returns defaults for ADMIN, SPONSOR, and SITE")
    void getAllRoleAuthorities_returnsConfigurableRoles() throws Exception {
        mockMvc.perform(get("/api/v1/system-admin/roles/authorities").header("Authorization", bearer(systemAdmin)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(3)))
                .andExpect(jsonPath("$[0].role").value("ADMIN"))
                .andExpect(jsonPath("$[1].role").value("SPONSOR"))
                .andExpect(jsonPath("$[2].role").value("SITE"));
    }

    @Test
    @DisplayName("PUT /api/v1/system-admin/roles/SITE/authorities without cascade updates template only")
    void updateRoleAuthorities_noCascade_leavesExistingUsersUnchanged() throws Exception {
        String payload = """
                {
                    "authorities": ["tenant:read", "tenant:update"],
                    "applyToExistingUsers": false,
                    "reason": "Updated default template"
                }
                """;

        mockMvc.perform(put("/api/v1/system-admin/roles/SITE/authorities")
                        .header("Authorization", bearer(systemAdmin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("SITE"))
                .andExpect(jsonPath("$.authorities", hasSize(2)));

        // Existing siteUser still has original authorities (tenant:read, patient:read)
        List<Authority> userAuths = userAuthorityRepository.findAuthoritiesByUserId(siteUser.getId());
        assertThat(userAuths).containsExactlyInAnyOrder(Authority.TENANT_READ, Authority.PATIENT_READ);
    }

    @Test
    @DisplayName("PUT /api/v1/system-admin/roles/SITE/authorities with cascade updates existing users and audits")
    void updateRoleAuthorities_cascade_updatesExistingUsersAndAudits() throws Exception {
        String payload = """
                {
                    "authorities": ["subtenant:create", "subtenant:manage"],
                    "applyToExistingUsers": true,
                    "reason": "Security reconfiguration"
                }
                """;

        mockMvc.perform(put("/api/v1/system-admin/roles/SITE/authorities")
                        .header("Authorization", bearer(systemAdmin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("SITE"))
                .andExpect(jsonPath("$.authorities", hasSize(2)));

        // Existing siteUser authorities cascaded
        List<Authority> userAuths = userAuthorityRepository.findAuthoritiesByUserId(siteUser.getId());
        assertThat(userAuths).containsExactlyInAnyOrder(Authority.SUBTENANT_CREATE, Authority.SUBTENANT_MANAGE);

        // Audit entry created
        var auditLogs = auditLogRepository.findAll();
        assertThat(auditLogs).anyMatch(log -> AuditService.ROLE_AUTHORITIES_CHANGED.equals(log.getAction()));
    }

    @Test
    @DisplayName("PUT /api/v1/system-admin/roles/SPONSOR/authorities with overlapping existing authorities succeeds")
    void updateRoleAuthorities_overlappingExistingAuthorities_succeeds() throws Exception {
        roleAuthorityRepository.save(RoleAuthorityEntity.builder().role(Role.SPONSOR).authority(Authority.TENANT_READ).build());
        roleAuthorityRepository.save(RoleAuthorityEntity.builder().role(Role.SPONSOR).authority(Authority.PATIENT_READ).build());

        UserEntity sponsorUser = saveUser("sponsor-overlap", Role.SPONSOR, rootTenant);
        userAuthorityRepository.save(UserAuthorityEntity.builder().user(sponsorUser).authority(Authority.TENANT_READ).build());
        userAuthorityRepository.save(UserAuthorityEntity.builder().user(sponsorUser).authority(Authority.PATIENT_READ).build());

        String payload = """
                {
                    "authorities": ["tenant:read", "role:read"],
                    "applyToExistingUsers": true,
                    "reason": "Test overlap update"
                }
                """;

        mockMvc.perform(put("/api/v1/system-admin/roles/SPONSOR/authorities")
                        .header("Authorization", bearer(systemAdmin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("SPONSOR"))
                .andExpect(jsonPath("$.authorities", hasSize(2)))
                .andExpect(jsonPath("$.authorities", containsInAnyOrder("tenant:read", "role:read")));

        List<Authority> userAuths = userAuthorityRepository.findAuthoritiesByUserId(sponsorUser.getId());
        assertThat(userAuths).containsExactlyInAnyOrder(Authority.TENANT_READ, Authority.ROLE_READ);
    }

    @Test
    @DisplayName("PUT /api/v1/system-admin/roles/{role}/authorities rejects SYSTEM_ADMIN and PATIENT")
    void updateRoleAuthorities_rejectsImmutableRoles() throws Exception {
        String payload = "{\"authorities\": [\"tenant:read\"], \"applyToExistingUsers\": false}";

        mockMvc.perform(put("/api/v1/system-admin/roles/SYSTEM_ADMIN/authorities")
                        .header("Authorization", bearer(systemAdmin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isBadRequest());

        mockMvc.perform(put("/api/v1/system-admin/roles/PATIENT/authorities")
                        .header("Authorization", bearer(systemAdmin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isBadRequest());
    }

    private UserEntity saveUser(String name, Role role, TenantEntity tenant) {
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
}
