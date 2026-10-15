package com.hekma.identity.dto;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.otp.VerificationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import com.hekma.identity.validation.StrongPassword;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
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
@Schema(description = "User registration request payload")
public class RegisterRequest {

    @Email(message = "Invalid email format")
    @Schema(description = "User's email address (at least one of email or phone is required)", example = "user@hekma.com")
    private String email;

    @NotBlank(message = "Password is required")
    @StrongPassword
    @Schema(description = "User's password (8-128 chars, upper, lower, digit, special)", example = "SecureP@ss123", requiredMode = Schema.RequiredMode.REQUIRED)
    private String password;

    @NotNull(message = "Role is required")
    @Schema(description = "Target role for registration. Only PATIENT is allowed for public self-registration", example = "PATIENT", requiredMode = Schema.RequiredMode.REQUIRED)
    private Role role;

    @Schema(description = "User's display or full name", example = "Jane Doe")
    private String displayName;

    @Schema(description = "User's registered phone number in E.164 format (at least one of email or phone is required)", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Verification mode through which user prefers to verify (PHONE or EMAIL)", example = "PHONE")
    private VerificationMode verificationMode;

    @Schema(description = "Clinical trial recruitment or invitation code if invited by a SITE or SPONSOR user", example = "INV-123456")
    private String invitationCode;
}

