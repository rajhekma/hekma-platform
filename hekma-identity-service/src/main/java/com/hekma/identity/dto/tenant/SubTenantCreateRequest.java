package com.hekma.identity.dto.tenant;

import com.hekma.identity.domain.TenantType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
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
@Schema(description = "Payload for creating a sub-tenant under an existing tenant")
public class SubTenantCreateRequest {

    @NotBlank(message = "Tenant name is required")
    @Size(min = 2, max = 255, message = "Tenant name must be between 2 and 255 characters")
    @Schema(description = "Sub-tenant organization name", example = "Mayo Clinic Rochester Site", requiredMode = Schema.RequiredMode.REQUIRED)
    private String name;

    @NotBlank(message = "Tenant slug is required")
    @Pattern(regexp = "^[a-z0-9]+(?:-[a-z0-9]+)*$", message = "Slug must be lowercase alphanumeric with hyphens (e.g. 'mayo-rochester')")
    @Size(min = 2, max = 100, message = "Slug must be between 2 and 100 characters")
    @Schema(description = "Unique URL slug", example = "mayo-rochester", requiredMode = Schema.RequiredMode.REQUIRED)
    private String slug;

    @NotNull(message = "Tenant type is required (SPONSOR or SITE)")
    @Schema(description = "Sub-tenant type (may differ from the parent's type)", example = "SITE", requiredMode = Schema.RequiredMode.REQUIRED)
    private TenantType tenantType;

    @Schema(description = "Subscription tier", example = "STANDARD")
    private String subscriptionTier;

    @Email(message = "Contact email must be a valid email address")
    @Schema(description = "Administrative contact email", example = "admin@mayo.edu")
    private String contactEmail;

    @Schema(description = "Administrative contact phone", example = "+15551234567")
    private String contactPhone;

    @Schema(description = "Settings JSON", example = "{\"region\":\"US-EAST\"}")
    private String settings;

    @Valid
    @Schema(description = "Optional first user (owner) of the sub-tenant")
    private TenantOwnerRequest owner;
}
