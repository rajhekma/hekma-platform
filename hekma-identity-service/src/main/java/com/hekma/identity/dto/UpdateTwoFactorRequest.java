package com.hekma.identity.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Payload to enable or disable Two-Factor Authentication (2FA)")
public class UpdateTwoFactorRequest {

    @NotNull(message = "twoFactorEnabled is required")
    @Schema(description = "Whether 2FA should be enabled or disabled", example = "true", requiredMode = Schema.RequiredMode.REQUIRED)
    private Boolean twoFactorEnabled;
}
