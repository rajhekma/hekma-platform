package com.hekma.identity.dto;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.VerificationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Response returned upon login attempt")
public class LoginResponse {

    @Schema(description = "Whether two-factor authentication (2FA) is required before session is granted", example = "false")
    private boolean twoFactorRequired;

    @Schema(description = "Informational message regarding the login result", example = "Login successful.")
    private String message;

    @Schema(description = "Firebase JWT ID token for API authentication (null if 2FA required)", example = "eyJhbGciOiJSUzI1NiIs...")
    private String idToken;

    @Schema(description = "OAuth2 refresh token (null if 2FA required)", example = "AMf-vBx...")
    private String refreshToken;

    @Schema(description = "Token type", example = "Bearer")
    private String tokenType;

    @Schema(description = "Token expiration duration in seconds", example = "3600")
    private Long expiresIn;

    @Schema(description = "Firebase custom token for client sign-in via signInWithCustomToken (if available)", example = "eyJhbGciOiJSUzI1NiIs...")
    private String firebaseCustomToken;

    @Schema(description = "OTP authentication attempt identifier (if 2FA required)", example = "550e8400-e29b-41d4-a716-446655440000")
    private UUID otpAttemptId;

    @Schema(description = "OTP expiration in seconds (if 2FA required)", example = "300")
    private Long otpExpiresInSeconds;

    @Schema(description = "Verification mode used for 2FA dispatch (PHONE or EMAIL)", example = "PHONE")
    private VerificationMode verificationMode;

    @Schema(description = "User unique UUID in PostgreSQL", example = "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6")
    private UUID userId;

    @Schema(description = "Firebase Authentication UID", example = "fb-usr-987654321")
    private String firebaseUid;

    @Schema(description = "User registered email", example = "user@hekma.com")
    private String email;

    @Schema(description = "User registered phone number", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Assigned user role", example = "PATIENT")
    private Role role;

    @Schema(description = "User display name", example = "John Doe")
    private String displayName;

    @Schema(description = "Account status", example = "ACTIVE")
    private UserStatus status;

    @Schema(description = "Whether the phone number is verified", example = "true")
    private Boolean phoneVerified;

    @Schema(description = "Whether the email is verified", example = "true")
    private Boolean emailVerified;

    @Schema(description = "Whether 2FA is enabled for this account", example = "false")
    private Boolean twoFactorEnabled;

    @Schema(description = "Associated tenant identifier")
    private UUID tenantId;

    @Schema(description = "Associated tenant slug")
    private String tenantSlug;
}

