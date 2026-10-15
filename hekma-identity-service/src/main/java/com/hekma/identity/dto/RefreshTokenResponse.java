package com.hekma.identity.dto;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Response containing refreshed authentication tokens and user details")
public class RefreshTokenResponse {

    @Schema(description = "New short-lived Firebase JWT ID Token", example = "eyJhbGciOiJSUzI1NiIs...")
    private String idToken;

    @Schema(description = "Firebase OAuth2 Refresh Token (may be rotated)", example = "AMf-vBx...")
    private String refreshToken;

    @Schema(description = "Token type (always Bearer)", example = "Bearer")
    private String tokenType;

    @Schema(description = "Token expiration duration in seconds", example = "3600")
    private Long expiresIn;

    @Schema(description = "Firebase Unique User Identifier (UID)", example = "fb-patient-12345")
    private String firebaseUid;

    @Schema(description = "Registered user email", example = "patient@example.com")
    private String email;

    @Schema(description = "Assigned user role", example = "PATIENT")
    private Role role;

    @Schema(description = "User display name", example = "Sarah Connor")
    private String displayName;

    @Schema(description = "Account status", example = "ACTIVE")
    private UserStatus status;
}
