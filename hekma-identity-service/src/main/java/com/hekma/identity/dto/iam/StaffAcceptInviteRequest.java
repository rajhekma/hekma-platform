package com.hekma.identity.dto.iam;

import com.hekma.identity.validation.StrongPassword;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
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
@Schema(description = "Accepts a staff invitation and creates the account")
public class StaffAcceptInviteRequest {

    @NotBlank(message = "Invitation token is required")
    @Schema(description = "Single-use token from the invitation email", requiredMode = Schema.RequiredMode.REQUIRED)
    private String token;

    @NotBlank(message = "Password is required")
    @StrongPassword
    @Schema(description = "Account password (8-128 chars, upper, lower, digit, special)", example = "SecurePassword123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String password;

    @Schema(description = "Display name", example = "Dr. Emily Watson")
    private String displayName;

    @Schema(description = "Phone number in E.164 format", example = "+15551234567")
    private String phoneNumber;
}
