package com.hekma.identity.service;

import com.hekma.identity.service.AuditService;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.dto.UpdateUserStatusRequest;
import com.hekma.identity.dto.UserResponse;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserInactiveException;
import com.hekma.identity.exception.UserNotFoundException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserManagementServiceTest {

    @Mock
    private UserRepository userRepository;

    @Mock
    private FirebaseService firebaseService;

    @Mock
    private AuditService auditService;

    @InjectMocks
    private UserManagementService userManagementService;

    private UserEntity systemAdminUser;
    private UserEntity adminUser1;
    private UserEntity adminUser2;
    private UserEntity sponsorUser;
    private UserEntity siteUser;
    private UserEntity patientUser;

    @BeforeEach
    void setUp() {
        systemAdminUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("sysadmin@hekma.com")
                .role(Role.SYSTEM_ADMIN)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();

        adminUser1 = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("admin1@hekma.com")
                .role(Role.ADMIN)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();

        adminUser2 = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("admin2@hekma.com")
                .role(Role.ADMIN)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();

        sponsorUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("sponsor@hekma.com")
                .role(Role.SPONSOR)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();

        siteUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("site@hekma.com")
                .role(Role.SITE)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();

        patientUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("patient@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();
    }

    // ==========================================
    // Hierarchy: SYSTEM_ADMIN operations
    // ==========================================

    @Test
    @DisplayName("SYSTEM_ADMIN can deactivate an ADMIN user")
    void systemAdmin_canDeactivate_adminUser() {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(false)
                .reason("Security audit")
                .build();

        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(invocation -> invocation.getArgument(0));

        UserResponse response = userManagementService.updateUserStatus(adminUser1.getId(), request, systemAdminUser.getId());

        assertThat(response.getIsActive()).isFalse();
        assertThat(response.getStatus()).isEqualTo(UserStatus.INACTIVE);
        assertThat(response.getMessage()).contains("INACTIVE");
        verify(userRepository).save(adminUser1);
    }

    @Test
    @DisplayName("SYSTEM_ADMIN can activate an ADMIN user")
    void systemAdmin_canActivate_adminUser() {
        adminUser1.setIsActive(false);
        adminUser1.setStatus(UserStatus.INACTIVE);

        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(true)
                .build();

        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(invocation -> invocation.getArgument(0));

        UserResponse response = userManagementService.updateUserStatus(adminUser1.getId(), request, systemAdminUser.getId());

        assertThat(response.getIsActive()).isTrue();
        assertThat(response.getStatus()).isEqualTo(UserStatus.ACTIVE);
        assertThat(response.getMessage()).contains("ACTIVE");
    }

    @Test
    @DisplayName("SYSTEM_ADMIN can deactivate SPONSOR, SITE, and PATIENT users")
    void systemAdmin_canDeactivate_belowUsers() {
        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(invocation -> invocation.getArgument(0));

        // Test Sponsor
        when(userRepository.findById(sponsorUser.getId())).thenReturn(Optional.of(sponsorUser));
        UserResponse sponsorResp = userManagementService.updateUserStatus(sponsorUser.getId(),
                UpdateUserStatusRequest.builder().isActive(false).build(), systemAdminUser.getId());
        assertThat(sponsorResp.getIsActive()).isFalse();

        // Test Site
        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));
        UserResponse siteResp = userManagementService.updateUserStatus(siteUser.getId(),
                UpdateUserStatusRequest.builder().isActive(false).build(), systemAdminUser.getId());
        assertThat(siteResp.getIsActive()).isFalse();

        // Test Patient
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        UserResponse patientResp = userManagementService.updateUserStatus(patientUser.getId(),
                UpdateUserStatusRequest.builder().isActive(false).build(), systemAdminUser.getId());
        assertThat(patientResp.getIsActive()).isFalse();
    }

    @Test
    @DisplayName("Modifying SYSTEM_ADMIN status is disallowed even by SYSTEM_ADMIN")
    void modifyingSystemAdminStatus_throwsUnauthorizedOperationException() {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(false)
                .build();

        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));

        assertThatThrownBy(() -> userManagementService.updateUserStatus(systemAdminUser.getId(), request, adminUser1.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("SYSTEM_ADMIN user status cannot be modified or deactivated");
    }

    // ==========================================
    // Hierarchy: ADMIN operations
    // ==========================================

    @Test
    @DisplayName("ADMIN can deactivate below users (SPONSOR, SITE, PATIENT)")
    void admin_canDeactivate_belowUsers() {
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(invocation -> invocation.getArgument(0));

        // Admin modifies Patient
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        UserResponse patientResp = userManagementService.updateUserStatus(patientUser.getId(),
                UpdateUserStatusRequest.builder().isActive(false).build(), adminUser1.getId());
        assertThat(patientResp.getIsActive()).isFalse();

        // Admin modifies Site
        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));
        UserResponse siteResp = userManagementService.updateUserStatus(siteUser.getId(),
                UpdateUserStatusRequest.builder().isActive(false).build(), adminUser1.getId());
        assertThat(siteResp.getIsActive()).isFalse();

        // Admin modifies Sponsor
        when(userRepository.findById(sponsorUser.getId())).thenReturn(Optional.of(sponsorUser));
        UserResponse sponsorResp = userManagementService.updateUserStatus(sponsorUser.getId(),
                UpdateUserStatusRequest.builder().isActive(false).build(), adminUser1.getId());
        assertThat(sponsorResp.getIsActive()).isFalse();
    }

    @Test
    @DisplayName("ADMIN cannot modify status of another ADMIN")
    void admin_cannotModify_anotherAdmin() {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(false)
                .build();

        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(adminUser2.getId())).thenReturn(Optional.of(adminUser2));

        assertThatThrownBy(() -> userManagementService.updateUserStatus(adminUser2.getId(), request, adminUser1.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("ADMIN users cannot modify the status of other ADMIN users. Only SYSTEM_ADMIN can modify an ADMIN user.");
    }

    @Test
    @DisplayName("ADMIN cannot modify status of SYSTEM_ADMIN")
    void admin_cannotModify_systemAdmin() {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(false)
                .build();

        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));

        assertThatThrownBy(() -> userManagementService.updateUserStatus(systemAdminUser.getId(), request, adminUser1.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("SYSTEM_ADMIN user status cannot be modified or deactivated");
    }

    // ==========================================
    // Hierarchy: Non-admin operations rejected
    // ==========================================

    @Test
    @DisplayName("PATIENT attempting to modify status throws UnauthorizedOperationException")
    void patient_modifyingStatus_throwsUnauthorizedOperationException() {
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(false)
                .build();

        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        when(userRepository.findById(sponsorUser.getId())).thenReturn(Optional.of(sponsorUser));

        assertThatThrownBy(() -> userManagementService.updateUserStatus(sponsorUser.getId(), request, patientUser.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("does not have permission to modify user status");
    }

    // ==========================================
    // Operator status validation
    // ==========================================

    @Test
    @DisplayName("Inactive operator cannot perform modifications")
    void inactiveOperator_throwsUserInactiveException() {
        adminUser1.setIsActive(false);
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));

        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder().isActive(false).build();

        assertThatThrownBy(() -> userManagementService.updateUserStatus(patientUser.getId(), request, adminUser1.getId()))
                .isInstanceOf(UserInactiveException.class)
                .hasMessageContaining("Operator account is inactive or suspended");
    }

    @Test
    @DisplayName("Operator not found throws UserNotFoundException")
    void operatorNotFound_throwsUserNotFoundException() {
        UUID unknownOperatorId = UUID.randomUUID();
        when(userRepository.findById(unknownOperatorId)).thenReturn(Optional.empty());

        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder().isActive(false).build();

        assertThatThrownBy(() -> userManagementService.updateUserStatus(patientUser.getId(), request, unknownOperatorId))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessageContaining("Operator user not found");
    }

    @Test
    @DisplayName("Target user not found throws UserNotFoundException")
    void targetNotFound_throwsUserNotFoundException() {
        UUID unknownTargetId = UUID.randomUUID();
        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));
        when(userRepository.findById(unknownTargetId)).thenReturn(Optional.empty());

        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder().isActive(false).build();

        assertThatThrownBy(() -> userManagementService.updateUserStatus(unknownTargetId, request, systemAdminUser.getId()))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessageContaining("Target user not found");
    }

    // ==========================================
    // Soft Deletion
    // ==========================================

    @Test
    @DisplayName("SYSTEM_ADMIN can soft-delete an ADMIN user")
    void systemAdmin_canSoftDelete_adminUser() {
        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(invocation -> invocation.getArgument(0));

        UserResponse response = userManagementService.softDeleteUser(adminUser1.getId(), systemAdminUser.getId());

        assertThat(response.getIsDeleted()).isTrue();
        assertThat(response.getIsActive()).isFalse();
        assertThat(response.getStatus()).isEqualTo(UserStatus.INACTIVE);
        assertThat(response.getMessage()).contains("soft-deleted successfully");
        verify(userRepository).save(adminUser1);
    }

    @Test
    @DisplayName("ADMIN can soft-delete a PATIENT user")
    void admin_canSoftDelete_patientUser() {
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(invocation -> invocation.getArgument(0));

        UserResponse response = userManagementService.softDeleteUser(patientUser.getId(), adminUser1.getId());

        assertThat(response.getIsDeleted()).isTrue();
        assertThat(response.getIsActive()).isFalse();
        assertThat(response.getStatus()).isEqualTo(UserStatus.INACTIVE);
    }

    @Test
    @DisplayName("ADMIN cannot soft-delete another ADMIN")
    void admin_cannotSoftDelete_anotherAdmin() {
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(adminUser2.getId())).thenReturn(Optional.of(adminUser2));

        assertThatThrownBy(() -> userManagementService.softDeleteUser(adminUser2.getId(), adminUser1.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("ADMIN users cannot modify the status of other ADMIN users");
    }

    @Test
    @DisplayName("Attempting to soft-delete SYSTEM_ADMIN throws UnauthorizedOperationException")
    void softDelete_systemAdmin_throwsUnauthorizedOperationException() {
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(systemAdminUser.getId())).thenReturn(Optional.of(systemAdminUser));

        assertThatThrownBy(() -> userManagementService.softDeleteUser(systemAdminUser.getId(), adminUser1.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("SYSTEM_ADMIN user status cannot be modified or deactivated");
    }

    // ==========================================
    // getUserById
    // ==========================================

    @Test
    @DisplayName("getUserById returns user response when user exists")
    void getUserById_userExists_returnsUserResponse() {
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));

        UserResponse response = userManagementService.getUserById(patientUser.getId(), principalOf(patientUser));

        assertThat(response.getId()).isEqualTo(patientUser.getId());
        assertThat(response.getEmail()).isEqualTo("patient@hekma.com");
        assertThat(response.getRole()).isEqualTo(Role.PATIENT);
        assertThat(response.getIsActive()).isTrue();
        assertThat(response.getIsDeleted()).isFalse();
    }

    @Test
    @DisplayName("getUserById throws UserNotFoundException when user does not exist")
    void getUserById_notFound_throwsUserNotFoundException() {
        UUID unknownId = UUID.randomUUID();
        when(userRepository.findById(unknownId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userManagementService.getUserById(unknownId, principalOf(adminUser1)))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessageContaining("User not found with ID");
    }

    // ==========================================
    // updateTwoFactor
    // ==========================================

    @Test
    @DisplayName("updateTwoFactor enables 2FA for active user successfully")
    void updateTwoFactor_enablesTwoFactor_successfully() {
        patientUser.setTwoFactorEnabled(false);
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        UserResponse response = userManagementService.updateTwoFactor(patientUser.getId(), true, principalOf(patientUser));

        assertThat(response.getTwoFactorEnabled()).isTrue();
        assertThat(response.getMessage()).contains("Two-factor authentication has been enabled");
        verify(userRepository).save(argThat(UserEntity::getTwoFactorEnabled));
    }

    @Test
    @DisplayName("updateTwoFactor disables 2FA for active user successfully")
    void updateTwoFactor_disablesTwoFactor_successfully() {
        patientUser.setTwoFactorEnabled(true);
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        UserResponse response = userManagementService.updateTwoFactor(patientUser.getId(), false, principalOf(patientUser));

        assertThat(response.getTwoFactorEnabled()).isFalse();
        assertThat(response.getMessage()).contains("Two-factor authentication has been disabled");
        verify(userRepository).save(argThat(u -> !u.getTwoFactorEnabled()));
    }

    @Test
    @DisplayName("updateTwoFactor for inactive user throws UserInactiveException")
    void updateTwoFactor_inactiveUser_throwsUserInactiveException() {
        patientUser.setIsActive(false);
        patientUser.setStatus(UserStatus.INACTIVE);
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));

        assertThatThrownBy(() -> userManagementService.updateTwoFactor(patientUser.getId(), true, principalOf(patientUser)))
                .isInstanceOf(UserInactiveException.class)
                .hasMessageContaining("inactive or suspended");
    }

    @Test
    @DisplayName("updateTwoFactor for non-existent user throws UserNotFoundException")
    void updateTwoFactor_notFound_throwsUserNotFoundException() {
        UUID unknownId = UUID.randomUUID();
        when(userRepository.findById(unknownId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userManagementService.updateTwoFactor(unknownId, true, principalOf(adminUser1)))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessageContaining("User not found with ID");
    }
    // ==========================================
    // Caller scoping & session revocation
    // ==========================================

    @Test
    @DisplayName("getUserById hides users outside the caller's scope (404)")
    void getUserById_otherUserForPatientCaller_throwsNotFound() {
        when(userRepository.findById(sponsorUser.getId())).thenReturn(Optional.of(sponsorUser));

        assertThatThrownBy(() -> userManagementService.getUserById(sponsorUser.getId(), principalOf(patientUser)))
                .isInstanceOf(UserNotFoundException.class);
    }

    @Test
    @DisplayName("getUserById allows platform administrators to read any user")
    void getUserById_platformAdmin_returnsUser() {
        when(userRepository.findById(sponsorUser.getId())).thenReturn(Optional.of(sponsorUser));

        UserResponse response = userManagementService.getUserById(sponsorUser.getId(), principalOf(adminUser1));

        assertThat(response.getId()).isEqualTo(sponsorUser.getId());
    }

    @Test
    @DisplayName("updateTwoFactor by another non-admin user is reported as not found")
    void updateTwoFactor_otherNonAdminCaller_throwsNotFound() {
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));

        assertThatThrownBy(() -> userManagementService.updateTwoFactor(patientUser.getId(), true, principalOf(sponsorUser)))
                .isInstanceOf(UserNotFoundException.class);
    }

    @Test
    @DisplayName("Operators cannot change the status of their own account")
    void updateUserStatus_selfTarget_throwsUnauthorized() {
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));

        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder().isActive(false).build();

        assertThatThrownBy(() -> userManagementService.updateUserStatus(adminUser1.getId(), request, adminUser1.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("own account");
    }

    @Test
    @DisplayName("Deactivating a user revokes all of its sessions")
    void updateUserStatus_deactivate_revokesSessions() {
        patientUser.setFirebaseUid("fb-patient");
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder().isActive(false).build();
        userManagementService.updateUserStatus(patientUser.getId(), request, adminUser1.getId());

        verify(firebaseService).revokeRefreshTokens("fb-patient");
    }

    @Test
    @DisplayName("Soft-deleting a user revokes all of its sessions")
    void softDeleteUser_revokesSessions() {
        patientUser.setFirebaseUid("fb-patient");
        when(userRepository.findById(adminUser1.getId())).thenReturn(Optional.of(adminUser1));
        when(userRepository.findById(patientUser.getId())).thenReturn(Optional.of(patientUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        userManagementService.softDeleteUser(patientUser.getId(), adminUser1.getId());

        verify(firebaseService).revokeRefreshTokens("fb-patient");
    }

    private static HekmaPrincipal principalOf(UserEntity user) {
        return new HekmaPrincipal(user.getId(), user.getFirebaseUid(), user.getEmail(), user.getRole(), user.getTenantId(),
                user.getTenant() != null ? user.getTenant().getPath() : null);
    }
}
