package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.dto.UpdateTwoFactorRequest;
import com.hekma.identity.dto.UpdateUserStatusRequest;
import com.hekma.identity.dto.UserResponse;
import com.hekma.identity.exception.GlobalExceptionHandler;
import com.hekma.identity.support.TestAuthentication;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserNotFoundException;
import com.hekma.identity.service.UserManagementService;
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
import java.util.Set;
import java.util.UUID;

import com.hekma.identity.dto.role.AssignCustomRolesRequest;
import com.hekma.identity.dto.role.CustomRoleResponse;
import com.hekma.identity.dto.role.UserCustomRolesResponse;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class UserControllerTest {

    private MockMvc mockMvc;

    @Mock
    private UserManagementService userManagementService;

    @Mock
    private com.hekma.identity.service.CustomRoleService customRoleService;

    @InjectMocks
    private UserController userController;

    private ObjectMapper objectMapper;

    private UUID targetUserId;
    private UUID operatorId;

    @AfterEach
    void tearDown() {
        TestAuthentication.clear();
    }

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(userController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new AuthenticationPrincipalArgumentResolver())
                .build();

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());

        targetUserId = UUID.randomUUID();
        operatorId = UUID.randomUUID();
        TestAuthentication.authenticate(operatorId, Role.ADMIN, null);
    }

    // ==========================================
    // PATCH /api/v1/users/{userId}/status
    // ==========================================

    @Test
    @DisplayName("PATCH /api/v1/users/{userId}/status returns 200 when status update succeeds")
    void updateUserStatus_validRequest_returns200() throws Exception {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(false)
                .reason("Under investigation")
                .build();

        UserResponse response = UserResponse.builder()
                .id(targetUserId)
                .email("patient@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.INACTIVE)
                .isActive(false)
                .isDeleted(false)
                .createdAt(Instant.now())
                .message("User status successfully updated to INACTIVE.")
                .build();

        when(userManagementService.updateUserStatus(eq(targetUserId), any(UpdateUserStatusRequest.class), eq(operatorId)))
                .thenReturn(response);

        mockMvc.perform(patch("/api/v1/users/{userId}/status", targetUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(targetUserId.toString()))
                .andExpect(jsonPath("$.isActive").value(false))
                .andExpect(jsonPath("$.status").value("INACTIVE"))
                .andExpect(jsonPath("$.message").value("User status successfully updated to INACTIVE."));
    }

    @Test
    @DisplayName("PATCH /api/v1/users/{userId}/status returns 400 when isActive is missing")
    void updateUserStatus_missingIsActive_returns400() throws Exception {
        String invalidPayload = "{\"reason\":\"missing active\"}";

        mockMvc.perform(patch("/api/v1/users/{userId}/status", targetUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(invalidPayload))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("PATCH /api/v1/users/{userId}/status returns 403 on hierarchy violation")
    void updateUserStatus_hierarchyViolation_returns403() throws Exception {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(false)
                .build();

        when(userManagementService.updateUserStatus(eq(targetUserId), any(UpdateUserStatusRequest.class), eq(operatorId)))
                .thenThrow(new UnauthorizedOperationException("ADMIN users cannot modify the status of other ADMIN users. Only SYSTEM_ADMIN can modify an ADMIN user."));

        mockMvc.perform(patch("/api/v1/users/{userId}/status", targetUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.message").value("ADMIN users cannot modify the status of other ADMIN users. Only SYSTEM_ADMIN can modify an ADMIN user."));
    }

    @Test
    @DisplayName("PATCH /api/v1/users/{userId}/status returns 404 when target user is not found")
    void updateUserStatus_targetNotFound_returns404() throws Exception {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(true)
                .build();

        when(userManagementService.updateUserStatus(eq(targetUserId), any(UpdateUserStatusRequest.class), eq(operatorId)))
                .thenThrow(new UserNotFoundException("Target user not found with ID: " + targetUserId));

        mockMvc.perform(patch("/api/v1/users/{userId}/status", targetUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("Target user not found with ID: " + targetUserId));
    }

    // ==========================================
    // DELETE /api/v1/users/{userId}
    // ==========================================

    @Test
    @DisplayName("DELETE /api/v1/users/{userId} returns 200 on successful soft delete")
    void softDeleteUser_validRequest_returns200() throws Exception {
        UserResponse response = UserResponse.builder()
                .id(targetUserId)
                .email("deleted@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.INACTIVE)
                .isActive(false)
                .isDeleted(true)
                .message("User soft-deleted successfully.")
                .build();

        when(userManagementService.softDeleteUser(targetUserId, operatorId)).thenReturn(response);

        mockMvc.perform(delete("/api/v1/users/{userId}", targetUserId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isDeleted").value(true))
                .andExpect(jsonPath("$.isActive").value(false))
                .andExpect(jsonPath("$.message").value("User soft-deleted successfully."));
    }

    @Test
    @DisplayName("DELETE /api/v1/users/{userId} returns 403 when trying to delete SYSTEM_ADMIN")
    void softDeleteUser_systemAdmin_returns403() throws Exception {
        when(userManagementService.softDeleteUser(targetUserId, operatorId))
                .thenThrow(new UnauthorizedOperationException("SYSTEM_ADMIN user status cannot be modified or deactivated."));

        mockMvc.perform(delete("/api/v1/users/{userId}", targetUserId))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.message").value("SYSTEM_ADMIN user status cannot be modified or deactivated."));
    }

    // ==========================================
    // GET /api/v1/users/{userId}
    // ==========================================

    @Test
    @DisplayName("GET /api/v1/users/{userId} returns 200 with user profile")
    void getUserById_userExists_returns200() throws Exception {
        UserResponse response = UserResponse.builder()
                .id(targetUserId)
                .email("alice@hekma.com")
                .role(Role.PATIENT)
                .displayName("Alice")
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();

        when(userManagementService.getUserById(eq(targetUserId), any())).thenReturn(response);

        mockMvc.perform(get("/api/v1/users/{userId}", targetUserId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(targetUserId.toString()))
                .andExpect(jsonPath("$.email").value("alice@hekma.com"))
                .andExpect(jsonPath("$.isActive").value(true))
                .andExpect(jsonPath("$.isDeleted").value(false));
    }

    @Test
    @DisplayName("GET /api/v1/users/{userId} returns 404 when user not found or soft-deleted")
    void getUserById_notFound_returns404() throws Exception {
        when(userManagementService.getUserById(eq(targetUserId), any()))
                .thenThrow(new UserNotFoundException("User not found with ID: " + targetUserId));

        mockMvc.perform(get("/api/v1/users/{userId}", targetUserId))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("User not found with ID: " + targetUserId));
    }

    // ==========================================
    // PATCH /api/v1/users/{userId}/2fa
    // ==========================================

    @Test
    @DisplayName("PATCH /api/v1/users/{userId}/2fa successfully enables 2FA and returns 200 OK")
    void updateTwoFactor_enable_returns200() throws Exception {
        UpdateTwoFactorRequest request = UpdateTwoFactorRequest.builder()
                .twoFactorEnabled(true)
                .build();

        UserResponse response = UserResponse.builder()
                .id(targetUserId)
                .email("alice@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .twoFactorEnabled(true)
                .message("Two-factor authentication has been enabled.")
                .build();

        when(userManagementService.updateTwoFactor(eq(targetUserId), eq(true), any())).thenReturn(response);

        mockMvc.perform(patch("/api/v1/users/{userId}/2fa", targetUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(targetUserId.toString()))
                .andExpect(jsonPath("$.twoFactorEnabled").value(true))
                .andExpect(jsonPath("$.message").value("Two-factor authentication has been enabled."));
    }

    @Test
    @DisplayName("PATCH /api/v1/users/{userId}/2fa with missing twoFactorEnabled returns 400 Bad Request")
    void updateTwoFactor_missingField_returns400() throws Exception {
        UpdateTwoFactorRequest request = new UpdateTwoFactorRequest();

        mockMvc.perform(patch("/api/v1/users/{userId}/2fa", targetUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("GET /api/v1/users/{userId}/custom-roles returns user's custom roles")
    void getUserCustomRoles_success() throws Exception {
        UserCustomRolesResponse response = UserCustomRolesResponse.builder()
                .userId(targetUserId)
                .userEmail("staff@site.com")
                .inheritedAuthorities(java.util.List.of("patient:read"))
                .customRoles(java.util.List.of())
                .build();

        when(customRoleService.getUserCustomRoles(eq(targetUserId), any())).thenReturn(response);

        mockMvc.perform(get("/api/v1/users/{userId}/custom-roles", targetUserId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(targetUserId.toString()))
                .andExpect(jsonPath("$.inheritedAuthorities[0]").value("patient:read"));
    }

    @Test
    @DisplayName("PUT /api/v1/users/{userId}/custom-roles assigns custom roles to user")
    void assignCustomRoles_success() throws Exception {
        AssignCustomRolesRequest request = AssignCustomRolesRequest.builder()
                .roleIds(Set.of(UUID.randomUUID()))
                .reason("Assigning site role")
                .build();

        UserCustomRolesResponse response = UserCustomRolesResponse.builder()
                .userId(targetUserId)
                .userEmail("staff@site.com")
                .inheritedAuthorities(java.util.List.of("patient:read", "patient:update"))
                .customRoles(java.util.List.of())
                .build();

        when(customRoleService.assignCustomRoles(eq(targetUserId), any(), any())).thenReturn(response);

        mockMvc.perform(put("/api/v1/users/{userId}/custom-roles", targetUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(targetUserId.toString()));
    }
}
