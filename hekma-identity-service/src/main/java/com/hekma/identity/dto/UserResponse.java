package com.hekma.identity.dto;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.VerificationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Detailed user profile response")
public class UserResponse {

    @Schema(description = "Internal unique user identifier (UUID)")
    private UUID id;

    @Schema(description = "Firebase Authentication UID")
    private String firebaseUid;

    @Schema(description = "Registered email address")
    private String email;

    @Schema(description = "Assigned user role")
    private Role role;

    @Schema(description = "User's display or full name")
    private String displayName;

    @Schema(description = "User's registered phone number")
    private String phoneNumber;

    @Schema(description = "Account lifecycle status (ACTIVE, INACTIVE, PENDING_VERIFICATION, SUSPENDED)")
    private UserStatus status;

    @Schema(description = "Whether the user account is currently active")
    private Boolean isActive;

    @Schema(description = "Whether the user has been soft-deleted")
    private Boolean isDeleted;

    @Schema(description = "Whether the user's phone number has been verified")
    private Boolean phoneVerified;

    @Schema(description = "Whether the user's email address has been verified")
    private Boolean emailVerified;

    @Schema(description = "Primary or last used verification mode (PHONE, EMAIL)")
    private VerificationMode verificationMode;

    @Schema(description = "Whether two-factor authentication (2FA) is enabled for this account", example = "false")
    private Boolean twoFactorEnabled;

    @Schema(description = "Account creation timestamp")
    private Instant createdAt;

    @Schema(description = "Account last updated timestamp")
    private Instant updatedAt;

    @Schema(description = "Associated tenant organization UUID (null for platform administrators)")
    private UUID tenantId;

    @Schema(description = "Associated tenant organization slug (null for platform administrators)")
    private String tenantSlug;

    @Schema(description = "Informational message regarding the operation")
    private String message;
}
