package com.hekma.identity.dto;

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
@Schema(description = "Result of a password change: all previous sessions are revoked and a fresh session is issued")
public class ChangePasswordResponse {

    @Schema(description = "New Firebase ID token to use as 'Authorization: Bearer <idToken>'")
    private String idToken;

    @Schema(description = "New Firebase refresh token")
    private String refreshToken;

    @Schema(description = "Token type", example = "Bearer")
    private String tokenType;

    @Schema(description = "ID token lifetime in seconds", example = "3600")
    private Long expiresIn;

    @Schema(description = "Result message", example = "Password changed successfully. Other sessions have been signed out.")
    private String message;
}
