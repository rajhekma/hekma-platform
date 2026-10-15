package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.identity.domain.Role;
import com.hekma.identity.dto.role.CreateCustomRoleRequest;
import com.hekma.identity.dto.role.CustomRoleResponse;
import com.hekma.identity.dto.role.UpdateCustomRoleRequest;
import com.hekma.identity.exception.GlobalExceptionHandler;
import com.hekma.identity.service.CustomRoleService;
import com.hekma.identity.support.TestAuthentication;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.security.web.method.annotation.AuthenticationPrincipalArgumentResolver;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class CustomRoleControllerTest {

    private MockMvc mockMvc;

    @Mock
    private CustomRoleService customRoleService;

    @InjectMocks
    private CustomRoleController customRoleController;

    private ObjectMapper objectMapper;

    @AfterEach
    void clearAuth() {
        TestAuthentication.clear();
    }

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(customRoleController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new AuthenticationPrincipalArgumentResolver())
                .build();

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());

        TestAuthentication.authenticate(UUID.randomUUID(), Role.ADMIN, null);
    }

    @Test
    @DisplayName("POST /api/v1/custom-roles creates a role")
    void createCustomRole_success() throws Exception {
        CreateCustomRoleRequest request = CreateCustomRoleRequest.builder()
                .name("Trial Lead")
                .code("TRIAL_LEAD")
                .description("Leads clinical study trials")
                .authorities(Set.of("patient:read", "patient:create"))
                .build();

        CustomRoleResponse response = CustomRoleResponse.builder()
                .id(UUID.randomUUID())
                .name("Trial Lead")
                .code("TRIAL_LEAD")
                .description("Leads clinical study trials")
                .authorities(List.of("patient:create", "patient:read"))
                .createdAt(Instant.now())
                .build();

        when(customRoleService.createCustomRole(any(), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/custom-roles")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value("TRIAL_LEAD"))
                .andExpect(jsonPath("$.name").value("Trial Lead"));
    }

    @Test
    @DisplayName("GET /api/v1/custom-roles lists visible custom roles")
    void listCustomRoles_success() throws Exception {
        CustomRoleResponse role1 = CustomRoleResponse.builder()
                .id(UUID.randomUUID())
                .name("Role One")
                .code("ROLE_1")
                .build();

        when(customRoleService.listCustomRoles(any(), any())).thenReturn(List.of(role1));

        mockMvc.perform(get("/api/v1/custom-roles"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].code").value("ROLE_1"));
    }

    @Test
    @DisplayName("GET /api/v1/custom-roles/{roleId} returns role details")
    void getCustomRole_success() throws Exception {
        UUID roleId = UUID.randomUUID();
        CustomRoleResponse response = CustomRoleResponse.builder()
                .id(roleId)
                .name("Role Detail")
                .code("DETAIL_ROLE")
                .build();

        when(customRoleService.getCustomRole(eq(roleId), any())).thenReturn(response);

        mockMvc.perform(get("/api/v1/custom-roles/{roleId}", roleId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(roleId.toString()))
                .andExpect(jsonPath("$.code").value("DETAIL_ROLE"));
    }

    @Test
    @DisplayName("PUT /api/v1/custom-roles/{roleId} updates a role")
    void updateCustomRole_success() throws Exception {
        UUID roleId = UUID.randomUUID();
        UpdateCustomRoleRequest request = UpdateCustomRoleRequest.builder()
                .name("Updated Name")
                .build();

        CustomRoleResponse response = CustomRoleResponse.builder()
                .id(roleId)
                .name("Updated Name")
                .code("DETAIL_ROLE")
                .build();

        when(customRoleService.updateCustomRole(eq(roleId), any(), any())).thenReturn(response);

        mockMvc.perform(put("/api/v1/custom-roles/{roleId}", roleId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Updated Name"));
    }

    @Test
    @DisplayName("DELETE /api/v1/custom-roles/{roleId} deletes a role")
    void deleteCustomRole_success() throws Exception {
        UUID roleId = UUID.randomUUID();
        doNothing().when(customRoleService).deleteCustomRole(eq(roleId), any());

        mockMvc.perform(delete("/api/v1/custom-roles/{roleId}", roleId))
                .andExpect(status().isNoContent());
    }
}
