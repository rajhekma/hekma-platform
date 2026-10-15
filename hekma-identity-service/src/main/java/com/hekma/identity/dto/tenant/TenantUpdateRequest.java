package com.hekma.identity.dto.tenant;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
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
@Schema(description = "Payload for updating tenant organization metadata")
public class TenantUpdateRequest {

    @Size(min = 2, max = 255, message = "Tenant name must be between 2 and 255 characters")
    @Schema(description = "Updated organization name", example = "Mayo Clinic Comprehensive Cancer Center")
    private String name;

    @Schema(description = "Subscription tier (STANDARD, ENTERPRISE, PILOT)", example = "ENTERPRISE")
    private String subscriptionTier;

    @Email(message = "Contact email must be a valid email address")
    @Schema(description = "Updated administrative contact email", example = "contact@mayo.edu")
    private String contactEmail;

    @Schema(description = "Updated contact phone number", example = "+15559876543")
    private String contactPhone;

    @Schema(description = "Updated settings JSON", example = "{\"region\":\"US-EAST\",\"mfaRequired\":true}")
    private String settings;
}
