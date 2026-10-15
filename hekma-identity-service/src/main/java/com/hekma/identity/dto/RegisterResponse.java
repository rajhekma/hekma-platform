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
@Schema(description = "Response returned upon successful user registration")
public class RegisterResponse {

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

    @Schema(description = "Account status")
    private UserStatus status;

    @Schema(description = "Whether the user's phone number is verified")
    private Boolean phoneVerified;

    @Schema(description = "Whether the user's email address is verified")
    private Boolean emailVerified;

    @Schema(description = "Verification mode selected for authentication (PHONE, EMAIL)")
    private VerificationMode verificationMode;

    @Schema(description = "Whether two-factor authentication (2FA) is enabled for this account", example = "false")
    private Boolean twoFactorEnabled;

    @Schema(description = "OTP authentication attempt identifier for verification")
    private UUID otpAttemptId;

    @Schema(description = "OTP validity in seconds")
    private Long otpExpiresInSeconds;

    @Schema(description = "Account creation timestamp")
    private Instant createdAt;

    @Schema(description = "Informational message")
    private String message;

    @Schema(description = "Associated tenant identifier")
    private UUID tenantId;

    @Schema(description = "Associated tenant slug")
    private String tenantSlug;
}

