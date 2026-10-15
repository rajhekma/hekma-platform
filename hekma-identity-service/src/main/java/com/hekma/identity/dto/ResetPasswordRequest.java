package com.hekma.identity.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import io.swagger.v3.oas.annotations.media.Schema;
import com.hekma.identity.validation.StrongPassword;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload for resetting password with verification code")
public class ResetPasswordRequest {

    @NotBlank(message = "Identifier is required")
    @Schema(description = "User registered email or phone", example = "admin@hekma.ai", requiredMode = Schema.RequiredMode.REQUIRED)
    private String identifier;

    @NotBlank(message = "Verification code is required")
    @Size(min = 6, max = 6, message = "OTP code must be 6 digits")
    @Schema(description = "6-digit OTP code", example = "123456", requiredMode = Schema.RequiredMode.REQUIRED)
    @JsonAlias({"code", "otp"})
    private String otpCode;

    @NotBlank(message = "New password is required")
    @StrongPassword
    @Schema(description = "New user password", example = "NewSecurePassword123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String newPassword;
}
