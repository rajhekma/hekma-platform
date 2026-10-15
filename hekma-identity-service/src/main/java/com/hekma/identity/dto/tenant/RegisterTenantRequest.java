package com.hekma.identity.dto.tenant;

import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.otp.VerificationMode;
import com.hekma.identity.validation.StrongPassword;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
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
@Schema(description = "Public self-registration of a new top-level tenant (organization) together with its owner user")
public class RegisterTenantRequest {

    @NotBlank(message = "Organization name is required")
    @Size(min = 2, max = 255, message = "Organization name must be between 2 and 255 characters")
    @Schema(description = "Organization name", example = "Mayo Clinic Research", requiredMode = Schema.RequiredMode.REQUIRED)
    private String tenantName;

    @NotBlank(message = "Organization slug is required")
    @Pattern(regexp = "^[a-z0-9]+(?:-[a-z0-9]+)*$", message = "Slug must be lowercase alphanumeric with hyphens (e.g. 'mayo-clinic')")
    @Size(min = 2, max = 100, message = "Slug must be between 2 and 100 characters")
    @Schema(description = "Unique URL slug", example = "mayo-clinic", requiredMode = Schema.RequiredMode.REQUIRED)
    private String tenantSlug;

    @NotNull(message = "Organization type is required (SPONSOR or SITE)")
    @Schema(description = "Organization type; the owner's role equals it", example = "SITE", requiredMode = Schema.RequiredMode.REQUIRED)
    private TenantType tenantType;

    @Email(message = "Email must be a valid email address")
    @Schema(description = "Owner's email (at least one of email or phone is required)", example = "owner@mayo.edu")
    private String email;

    @Schema(description = "Owner's phone number in E.164 format", example = "+15551234567")
    private String phoneNumber;

    @NotBlank(message = "Password is required")
    @StrongPassword
    @Schema(description = "Owner's password (8-128 chars, upper, lower, digit, special)", example = "SecurePassword123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String password;

    @Schema(description = "Owner's display name", example = "Dr. Emily Watson")
    private String displayName;

    @Schema(description = "Channel for the verification OTP (defaults to PHONE when a phone number is given)", example = "EMAIL")
    private VerificationMode verificationMode;
}
