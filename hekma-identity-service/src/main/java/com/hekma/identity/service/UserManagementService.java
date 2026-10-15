package com.hekma.identity.service;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.dto.UpdateUserStatusRequest;
import com.hekma.identity.dto.UserResponse;
import com.hekma.identity.dto.iam.MeResponse;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserInactiveException;
import com.hekma.identity.exception.UserNotFoundException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@Transactional
@Slf4j
public class UserManagementService {

    private final UserRepository userRepository;
    private final FirebaseService firebaseService;
    private final AuditService auditService;

    public UserManagementService(UserRepository userRepository, FirebaseService firebaseService, AuditService auditService) {
        this.userRepository = userRepository;
        this.firebaseService = firebaseService;
        this.auditService = auditService;
    }

    /**
     * Lists users visible to the caller, optionally filtered by role. Platform administrators see every user;
     * SPONSOR/SITE users holding {@code user:read} see users of their tenant subtree.
     */
    @Transactional(readOnly = true)
    public Page<UserResponse> listUsers(Role role, Pageable pageable, HekmaPrincipal caller) {
        Page<UserEntity> page;
        if (caller.isPlatformAdmin()) {
            page = role != null ? userRepository.findByRole(role, pageable) : userRepository.findAll(pageable);
        } else if (caller.isTenantStaff() && caller.has(Authority.USER_READ) && caller.tenantPath() != null) {
            page = role != null
                    ? userRepository.findByTenant_PathStartingWithAndRole(caller.tenantPath(), role, pageable)
                    : userRepository.findByTenant_PathStartingWith(caller.tenantPath(), pageable);
        } else {
            throw new UnauthorizedOperationException("Listing users requires the user:read authority.");
        }
        return page.map(user -> toUserResponse(user, null));
    }

    /**
     * The authenticated caller's own profile, tenant position and effective authorities.
     */
    @Transactional(readOnly = true)
    public MeResponse me(HekmaPrincipal caller) {
        UserEntity user = userRepository.findById(caller.userId())
                .orElseThrow(() -> new UserNotFoundException("User not found with ID: " + caller.userId()));
        TenantEntity tenant = user.getTenant();
        return MeResponse.builder()
                .userId(user.getId())
                .email(user.getEmail())
                .phoneNumber(user.getPhoneNumber())
                .displayName(user.getDisplayName())
                .role(user.getRole())
                .status(user.getStatus())
                .twoFactorEnabled(Boolean.TRUE.equals(user.getTwoFactorEnabled()))
                .tenantId(tenant != null ? tenant.getId() : null)
                .tenantName(tenant != null ? tenant.getName() : null)
                .tenantSlug(tenant != null ? tenant.getSlug() : null)
                .tenantType(tenant != null ? tenant.getTenantType() : null)
                .tenantPath(tenant != null ? tenant.getPath() : null)
                .authorities(caller.authorities().stream().map(Authority::key).sorted().toList())
                .customRoles(caller.customRoles() != null ? caller.customRoles().stream().sorted().toList() : java.util.List.of())
                .build();
    }

    /**
     * Updates the active/inactive status of a target user, enforcing role-based hierarchy:
     * - SYSTEM_ADMIN can update active status of ADMIN, SPONSOR, SITE, PATIENT.
     * - SYSTEM_ADMIN cannot be deactivated.
     * - ADMIN can update active status of below users: SPONSOR, SITE, PATIENT.
     * - ADMIN cannot update status of ADMIN or SYSTEM_ADMIN.
     * - Other roles cannot modify user status.
     * - Nobody can modify their own account status.
     * Deactivation revokes all existing sessions of the target user.
     *
     * @param targetUserId ID of the user to update
     * @param request UpdateUserStatusRequest containing target isActive status
     * @param operatorId ID of the authenticated operator (taken from the verified access token)
     * @return UserResponse with updated user details
     */
    public UserResponse updateUserStatus(UUID targetUserId, UpdateUserStatusRequest request, UUID operatorId) {
        UserEntity operator = loadActiveOperator(operatorId);

        UserEntity target = userRepository.findById(targetUserId)
                .orElseThrow(() -> new UserNotFoundException("Target user not found with ID: " + targetUserId));

        validateHierarchy(operator, target);

        boolean targetIsActive = Boolean.TRUE.equals(request.getIsActive());
        target.setIsActive(targetIsActive);
        target.setStatus(targetIsActive ? UserStatus.ACTIVE : UserStatus.INACTIVE);

        UserStatus before = target.getStatus();
        UserEntity updated = userRepository.save(target);
        if (!targetIsActive) {
            firebaseService.revokeRefreshTokens(updated.getFirebaseUid());
        }
        auditService.record(operator.getId(), AuditService.USER_STATUS_CHANGED, AuditService.TARGET_USER,
                updated.getId(), updated.getTenantId(), String.valueOf(before),
                targetIsActive ? "ACTIVE" : "INACTIVE", request.getReason());
        log.info("User {} ({}) status updated to isActive={} by operator {} ({})",
                updated.getEmail(), updated.getRole(), targetIsActive, operator.getEmail(), operator.getRole());

        String message = "User status successfully updated to " + (targetIsActive ? "ACTIVE" : "INACTIVE") + ".";
        return toUserResponse(updated, message);
    }

    /**
     * Soft-deletes a user, setting isDeleted=true, isActive=false, and status=INACTIVE.
     * Enforces the same role-based hierarchy and revokes all existing sessions of the target user.
     *
     * @param targetUserId ID of the user to soft-delete
     * @param operatorId ID of the authenticated operator (taken from the verified access token)
     * @return UserResponse with soft-deleted user details
     */
    public UserResponse softDeleteUser(UUID targetUserId, UUID operatorId) {
        UserEntity operator = loadActiveOperator(operatorId);

        UserEntity target = userRepository.findById(targetUserId)
                .orElseThrow(() -> new UserNotFoundException("Target user not found with ID: " + targetUserId));

        validateHierarchy(operator, target);

        target.setIsDeleted(true);
        target.setIsActive(false);
        target.setStatus(UserStatus.INACTIVE);

        UserEntity deleted = userRepository.save(target);
        firebaseService.revokeRefreshTokens(deleted.getFirebaseUid());
        auditService.record(operator.getId(), AuditService.USER_SOFT_DELETED, AuditService.TARGET_USER,
                deleted.getId(), deleted.getTenantId(), null, "DELETED", null);
        log.info("User {} ({}) was soft-deleted by operator {} ({})",
                deleted.getEmail(), deleted.getRole(), operator.getEmail(), operator.getRole());

        return toUserResponse(deleted, "User soft-deleted successfully.");
    }

    /**
     * Validates that the operator is permitted to modify the target user according to role hierarchy:
     * - Operator cannot target itself
     * - Target cannot be SYSTEM_ADMIN (root account protection)
     * - SYSTEM_ADMIN can manage ADMIN, SPONSOR, SITE, PATIENT
     * - ADMIN can manage SPONSOR, SITE, PATIENT
     * - ADMIN cannot manage ADMIN or SYSTEM_ADMIN
     * - SPONSOR / SITE (with user:manage, enforced at the endpoint) manage SPONSOR, SITE and PATIENT users of their
     *   tenant subtree; users outside it are reported as not found
     * - PATIENT cannot manage any user
     */
    public void validateHierarchy(UserEntity operator, UserEntity target) {
        if (operator.getId() != null && operator.getId().equals(target.getId())) {
            throw new UnauthorizedOperationException("Users cannot modify the status of their own account.");
        }

        if (target.getRole() == Role.SYSTEM_ADMIN) {
            throw new UnauthorizedOperationException("SYSTEM_ADMIN user status cannot be modified or deactivated.");
        }

        if (operator.getRole() == Role.SYSTEM_ADMIN) {
            // SYSTEM_ADMIN is authorized to manage ADMIN, SPONSOR, SITE, PATIENT
            return;
        }

        if (operator.getRole() == Role.ADMIN) {
            if (target.getRole() == Role.ADMIN) {
                throw new UnauthorizedOperationException("ADMIN users cannot modify the status of other ADMIN users. Only SYSTEM_ADMIN can modify an ADMIN user.");
            }
            if (target.getRole() != Role.SPONSOR && target.getRole() != Role.SITE && target.getRole() != Role.PATIENT) {
                throw new UnauthorizedOperationException("ADMIN users can only modify status of users below them (SPONSOR, SITE, PATIENT).");
            }
            return;
        }

        if (operator.getRole() == Role.SPONSOR || operator.getRole() == Role.SITE) {
            if (operator.getTenant() == null || target.getTenant() == null
                    || !operator.getTenant().containsInSubtree(target.getTenant())) {
                throw new UserNotFoundException("Target user not found with ID: " + target.getId());
            }
            return;
        }

        throw new UnauthorizedOperationException("User role '" + operator.getRole() + "' does not have permission to modify user status.");
    }

    /**
     * Retrieves user profile details by ID, scoped to the caller:
     * - the user itself, or
     * - SYSTEM_ADMIN / ADMIN, or
     * - SPONSOR / SITE users holding user:read, for users of their own tenant and its sub-tenants.
     * Users outside the caller's scope are reported as not found.
     */
    @Transactional(readOnly = true)
    public UserResponse getUserById(UUID userId, HekmaPrincipal caller) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("User not found with ID: " + userId));

        boolean self = user.getId().equals(caller.userId());
        boolean inSubtree = user.getTenant() != null && caller.has(Authority.USER_READ) && caller.canSeeTenant(user.getTenant());
        if (!self && !caller.isPlatformAdmin() && !inSubtree) {
            throw new UserNotFoundException("User not found with ID: " + userId);
        }
        return toUserResponse(user, null);
    }

    /**
     * Updates two-factor authentication (2FA) preference for a user (primarily PATIENT profile).
     * Allowed for the user itself and for SYSTEM_ADMIN / ADMIN.
     *
     * @param userId ID of the user
     * @param twoFactorEnabled desired 2FA state
     * @param caller the authenticated caller
     * @return UserResponse with updated 2FA setting
     */
    public UserResponse updateTwoFactor(UUID userId, boolean twoFactorEnabled, HekmaPrincipal caller) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("User not found with ID: " + userId));

        if (!user.getId().equals(caller.userId()) && !caller.isPlatformAdmin()) {
            throw new UserNotFoundException("User not found with ID: " + userId);
        }

        if (!Boolean.TRUE.equals(user.getIsActive()) || user.getStatus() != UserStatus.ACTIVE) {
            throw new UserInactiveException("User account is inactive or suspended. Cannot update 2FA settings.");
        }

        user.setTwoFactorEnabled(twoFactorEnabled);
        UserEntity updated = userRepository.save(user);
        log.info("User {} ({}) updated twoFactorEnabled to {}", updated.getEmail(), updated.getId(), twoFactorEnabled);

        String message = twoFactorEnabled
                ? "Two-factor authentication has been enabled."
                : "Two-factor authentication has been disabled.";
        return toUserResponse(updated, message);
    }

    private UserEntity loadActiveOperator(UUID operatorId) {
        if (operatorId == null) {
            throw new UnauthorizedOperationException("An authenticated operator is required for this operation.");
        }
        UserEntity operator = userRepository.findById(operatorId)
                .orElseThrow(() -> new UserNotFoundException("Operator user not found with ID: " + operatorId));

        if (!Boolean.TRUE.equals(operator.getIsActive()) || operator.getStatus() != UserStatus.ACTIVE) {
            throw new UserInactiveException("Operator account is inactive or suspended. Cannot perform administrative operations.");
        }
        return operator;
    }

    public UserResponse toUserResponse(UserEntity user, String message) {
        return UserResponse.builder()
                .id(user.getId())
                .firebaseUid(user.getFirebaseUid())
                .email(user.getEmail())
                .role(user.getRole())
                .displayName(user.getDisplayName())
                .phoneNumber(user.getPhoneNumber())
                .status(user.getStatus())
                .isActive(user.getIsActive())
                .isDeleted(user.getIsDeleted())
                .phoneVerified(user.getPhoneVerified())
                .emailVerified(user.getEmailVerified())
                .twoFactorEnabled(Boolean.TRUE.equals(user.getTwoFactorEnabled()))
                .verificationMode(user.getVerificationMode())
                .createdAt(user.getCreatedAt())
                .updatedAt(user.getUpdatedAt())
                .tenantId(user.getTenantId())
                .tenantSlug(user.getTenant() != null ? user.getTenant().getSlug() : null)
                .message(message)
                .build();
    }
}
