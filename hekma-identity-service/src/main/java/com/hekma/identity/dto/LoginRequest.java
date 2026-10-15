package com.hekma.identity.dto;

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
@Schema(description = "User login credentials payload")
public class LoginRequest {

    @Schema(description = "Registered email address", example = "user@hekma.com")
    private String email;

    @Schema(description = "Registered phone number in E.164 format (for phone-registered patients)", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Universal identifier (can be email or phone number)", example = "user@hekma.com")
    private String identifier;

    @NotBlank(message = "Password is required")
    @Schema(description = "User password", example = "SecurePassword123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String password;
}
