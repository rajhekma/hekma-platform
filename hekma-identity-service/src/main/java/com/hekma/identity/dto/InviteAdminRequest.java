package com.hekma.identity.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import com.hekma.identity.validation.StrongPassword;
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
@Schema(description = "Request payload for creating/inviting an ADMIN user")
public class InviteAdminRequest {

    @NotBlank(message = "Email is required")
    @Email(message = "Invalid email format")
    @Schema(description = "Admin's email address", example = "admin@hekma.com", requiredMode = Schema.RequiredMode.REQUIRED)
    private String email;

    @NotBlank(message = "Temporary password is required")
    @StrongPassword
    @Schema(description = "Temporary initial password (8-128 chars, upper, lower, digit, special)", example = "AdminTempPass123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String temporaryPassword;

    @Schema(description = "Admin's display or full name", example = "Admin User")
    private String displayName;
}
