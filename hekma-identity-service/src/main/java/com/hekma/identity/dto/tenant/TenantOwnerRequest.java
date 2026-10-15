package com.hekma.identity.dto.tenant;

import com.hekma.identity.validation.StrongPassword;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
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
@Schema(description = "First user of a new sub-tenant. Its role equals the sub-tenant's type (SPONSOR or SITE).")
public class TenantOwnerRequest {

    @NotBlank(message = "Owner email is required")
    @Email(message = "Owner email must be a valid email address")
    @Schema(description = "Owner's email address", example = "coordinator@mayo.edu", requiredMode = Schema.RequiredMode.REQUIRED)
    private String email;

    @Schema(description = "Owner's display name", example = "Dr. Emily Watson")
    private String displayName;

    @Schema(description = "Owner's phone number in E.164 format", example = "+15551234567")
    private String phoneNumber;

    @NotBlank(message = "Temporary password is required")
    @StrongPassword
    @Schema(description = "Temporary password; the owner should change it after first login", example = "TempPassword123!", requiredMode = Schema.RequiredMode.REQUIRED)
    private String temporaryPassword;
}
