package com.hekma.identity.dto.otp;

import com.hekma.identity.domain.Role;
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
@Schema(description = "Response confirming successful OTP verification and authentication")
public class VerifyOtpResponse {

    @Schema(description = "Whether the OTP was verified successfully", example = "true")
    private boolean verified;

    @Schema(description = "Authentication attempt identifier", example = "550e8400-e29b-41d4-a716-446655440000")
    private UUID attemptId;

    @Schema(description = "Verified phone number", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Verified email address", example = "patient@hekma.com")
    private String email;

    @Schema(description = "Whether the user's phone number is verified", example = "true")
    private Boolean phoneVerified;

    @Schema(description = "Whether the user's email address is verified", example = "true")
    private Boolean emailVerified;

    @Schema(description = "Verification mode used for authentication (PHONE, EMAIL)", example = "PHONE")
    private VerificationMode verificationMode;

    @Schema(description = "Whether two-factor authentication (2FA) is enabled for this account", example = "false")
    private Boolean twoFactorEnabled;

    @Schema(description = "Firebase custom token for client sign-in via signInWithCustomToken", example = "eyJhbGciOiJSUzI1NiIs...")
    private String firebaseCustomToken;

    @Schema(description = "Firebase ID token to send as 'Authorization: Bearer <idToken>' (issued when the OTP belongs to a registered user)", example = "eyJhbGciOiJSUzI1NiIs...")
    private String idToken;

    @Schema(description = "Firebase refresh token for POST /api/v1/auth/refresh-token")
    private String refreshToken;

    @Schema(description = "Token type", example = "Bearer")
    private String tokenType;

    @Schema(description = "ID token lifetime in seconds", example = "3600")
    private Long expiresIn;

    @Schema(description = "User database UUID (if registered)", example = "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6")
    private UUID userId;

    @Schema(description = "Firebase UID", example = "fb-usr-987654321")
    private String firebaseUid;

    @Schema(description = "User role", example = "PATIENT")
    private Role role;

    @Schema(description = "User display name", example = "Sarah Connor")
    private String displayName;

    @Schema(description = "Tenant UUID", example = "00000000-0000-0000-0000-000000000001")
    private UUID tenantId;

    @Schema(description = "Tenant slug", example = "default-tenant")
    private String tenantSlug;

    @Schema(description = "User account status", example = "ACTIVE")
    private String status;

    @Schema(description = "Status message", example = "OTP verified successfully.")
    private String message;
}
