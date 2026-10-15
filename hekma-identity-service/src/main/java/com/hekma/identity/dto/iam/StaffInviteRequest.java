package com.hekma.identity.dto.iam;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;
import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Invitation of a SPONSOR/SITE user into a tenant. The role always equals the tenant's type.")
public class StaffInviteRequest {

    @NotBlank(message = "Email is required")
    @Email(message = "Email must be a valid email address")
    @Schema(description = "Invitee's email address", example = "coordinator@mayo.edu", requiredMode = Schema.RequiredMode.REQUIRED)
    private String email;

    @NotNull(message = "tenantId is required")
    @Schema(description = "Target tenant: the inviter's tenant or one of its sub-tenants", requiredMode = Schema.RequiredMode.REQUIRED)
    private UUID tenantId;

    @Schema(description = "Authority keys granted on acceptance (must be held by the inviter). "
            + "Default: tenant:read, patient:read, patient:create, limited to those the inviter holds.")
    private List<String> authorities;
}
