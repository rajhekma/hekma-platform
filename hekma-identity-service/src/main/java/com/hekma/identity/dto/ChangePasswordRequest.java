package com.hekma.identity.dto;

import com.hekma.identity.validation.StrongPassword;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload for changing the authenticated user's password")
public class ChangePasswordRequest {

    @NotBlank(message = "Current password is required")
    @Schema(description = "The user's current password", example = "OldSecurePassword123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String currentPassword;

    @NotBlank(message = "New password is required")
    @StrongPassword
    @Schema(description = "The new password (8-128 chars, upper, lower, digit, special)", example = "NewSecurePassword123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String newPassword;
}
