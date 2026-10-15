package com.hekma.identity.dto.role;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.Set;
import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Payload to define a new custom role")
public class CreateCustomRoleRequest {

    @NotBlank(message = "Role name is required.")
    @Size(max = 100, message = "Role name must not exceed 100 characters.")
    @Schema(description = "Human-readable role name", example = "Clinical Research Associate")
    private String name;

    @NotBlank(message = "Role code is required.")
    @Pattern(regexp = "^[A-Za-z0-9_-]+$", message = "Role code must contain only letters, numbers, hyphens, and underscores.")
    @Size(max = 50, message = "Role code must not exceed 50 characters.")
    @Schema(description = "Unique alphanumeric role code identifier", example = "CRA")
    private String code;

    @Size(max = 255, message = "Description must not exceed 255 characters.")
    @Schema(description = "Role description", example = "Monitors trial sites and participant adherence")
    private String description;

    @Schema(description = "Owning tenant ID (optional; derived from caller if tenant staff)", example = "00000000-0000-0000-0000-000000000001")
    private UUID tenantId;

    @NotEmpty(message = "At least one authority must be assigned to the role.")
    @Schema(description = "List of authority keys bundled in this role", example = "[\"patient:read\", \"patient:update\"]")
    private Set<String> authorities;
}
