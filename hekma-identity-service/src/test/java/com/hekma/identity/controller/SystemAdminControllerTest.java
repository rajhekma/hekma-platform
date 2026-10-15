package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.dto.InviteAdminRequest;
import com.hekma.identity.dto.RegisterResponse;
import com.hekma.identity.exception.GlobalExceptionHandler;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.service.AuthService;
import com.hekma.identity.service.RoleAuthorityService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class SystemAdminControllerTest {

    private MockMvc mockMvc;

    @Mock
    private AuthService authService;

    @Mock
    private RoleAuthorityService roleAuthorityService;

    @InjectMocks
    private SystemAdminController systemAdminController;

    private ObjectMapper objectMapper;

    @org.junit.jupiter.api.AfterEach
    void clearAuthentication() {
        com.hekma.identity.support.TestAuthentication.clear();
    }

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(systemAdminController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new org.springframework.security.web.method.annotation.AuthenticationPrincipalArgumentResolver())
                .build();
        com.hekma.identity.support.TestAuthentication.authenticate(UUID.randomUUID(), com.hekma.identity.domain.Role.SYSTEM_ADMIN, null);

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
    }

    @Test
    @DisplayName("POST /api/v1/system-admin/invite-admin returns 201 Created with valid payload")
    void inviteAdmin_validRequest_returns201() throws Exception {
        InviteAdminRequest request = InviteAdminRequest.builder()
                .email("admin@hekma.com")
                .temporaryPassword("AdminPass123!")
                .displayName("Site Admin")
                .build();

        RegisterResponse response = RegisterResponse.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-admin-01")
                .email("admin@hekma.com")
                .role(Role.ADMIN)
                .displayName("Site Admin")
                .status(UserStatus.ACTIVE)
                .createdAt(Instant.now())
                .message("Admin user invited successfully.")
                .build();

        when(authService.inviteAdmin(any(InviteAdminRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/system-admin/invite-admin")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email").value("admin@hekma.com"))
                .andExpect(jsonPath("$.role").value("ADMIN"))
                .andExpect(jsonPath("$.firebaseUid").value("fb-admin-01"))
                .andExpect(jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    @DisplayName("POST /api/v1/system-admin/invite-admin returns 400 Bad Request on invalid email")
    void inviteAdmin_invalidEmail_returns400() throws Exception {
        InviteAdminRequest request = InviteAdminRequest.builder()
                .email("invalid-email")
                .temporaryPassword("AdminPass123!")
                .displayName("Site Admin")
                .build();

        mockMvc.perform(post("/api/v1/system-admin/invite-admin")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("POST /api/v1/system-admin/invite-admin returns 400 Bad Request on short password")
    void inviteAdmin_shortPassword_returns400() throws Exception {
        InviteAdminRequest request = InviteAdminRequest.builder()
                .email("admin@hekma.com")
                .temporaryPassword("short")
                .displayName("Site Admin")
                .build();

        mockMvc.perform(post("/api/v1/system-admin/invite-admin")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("POST /api/v1/system-admin/invite-admin returns 409 Conflict when user already exists")
    void inviteAdmin_duplicateEmail_returns409() throws Exception {
        InviteAdminRequest request = InviteAdminRequest.builder()
                .email("existing.admin@hekma.com")
                .temporaryPassword("AdminPass123!")
                .displayName("Existing Admin")
                .build();

        when(authService.inviteAdmin(any(InviteAdminRequest.class), any()))
                .thenThrow(new UserAlreadyExistsException("A user with email 'existing.admin@hekma.com' is already registered in the system."));

        mockMvc.perform(post("/api/v1/system-admin/invite-admin")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.message", containsString("already registered")));
    }

    @Test
    @DisplayName("GET /api/v1/system-admin/authorities returns 200 with authority catalogue")
    void getAuthorities_returns200() throws Exception {
        when(roleAuthorityService.getAuthorityCatalogue()).thenReturn(java.util.List.of(
                com.hekma.identity.dto.iam.AuthorityDefinitionResponse.builder()
                        .key("tenant:read")
                        .name("View Tenant Hierarchy")
                        .category("Tenant Governance")
                        .description("View own tenant and descendant tenants")
                        .allowedRoles(java.util.List.of("ADMIN", "SPONSOR", "SITE"))
                        .build()
        ));

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/v1/system-admin/authorities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].key").value("tenant:read"))
                .andExpect(jsonPath("$[0].name").value("View Tenant Hierarchy"))
                .andExpect(jsonPath("$[0].category").value("Tenant Governance"));
    }

    @Test
    @DisplayName("GET /api/v1/system-admin/roles/authorities returns 200 with all configurable roles")
    void getAllRoleAuthorities_returns200() throws Exception {
        when(roleAuthorityService.getAllRoleAuthorities()).thenReturn(java.util.List.of(
                com.hekma.identity.dto.iam.RoleAuthoritiesResponse.builder()
                        .role(Role.ADMIN)
                        .authorities(java.util.List.of("tenant:read", "user:read"))
                        .totalAuthorities(2)
                        .build()
        ));

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/v1/system-admin/roles/authorities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].role").value("ADMIN"))
                .andExpect(jsonPath("$[0].totalAuthorities").value(2));
    }

    @Test
    @DisplayName("GET /api/v1/system-admin/roles/SITE/authorities returns 200 with SITE default authorities")
    void getRoleAuthorities_returns200() throws Exception {
        when(roleAuthorityService.getRoleAuthoritiesResponse(Role.SITE)).thenReturn(
                com.hekma.identity.dto.iam.RoleAuthoritiesResponse.builder()
                        .role(Role.SITE)
                        .authorities(java.util.List.of("tenant:read", "patient:read"))
                        .totalAuthorities(2)
                        .build()
        );

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/v1/system-admin/roles/SITE/authorities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("SITE"))
                .andExpect(jsonPath("$.authorities[0]").value("tenant:read"));
    }

    @Test
    @DisplayName("PUT /api/v1/system-admin/roles/SITE/authorities returns 200 on valid update")
    void updateRoleAuthorities_valid_returns200() throws Exception {
        com.hekma.identity.dto.iam.UpdateRoleAuthoritiesRequest request = com.hekma.identity.dto.iam.UpdateRoleAuthoritiesRequest.builder()
                .authorities(java.util.List.of("tenant:read", "patient:read"))
                .applyToExistingUsers(true)
                .reason("Security update")
                .build();

        when(roleAuthorityService.updateRoleAuthorities(any(), any(), any(Boolean.class), any(), any()))
                .thenReturn(com.hekma.identity.dto.iam.RoleAuthoritiesResponse.builder()
                        .role(Role.SITE)
                        .authorities(java.util.List.of("patient:read", "tenant:read"))
                        .totalAuthorities(2)
                        .build());

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put("/api/v1/system-admin/roles/SITE/authorities")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("SITE"))
                .andExpect(jsonPath("$.totalAuthorities").value(2));
    }
}
