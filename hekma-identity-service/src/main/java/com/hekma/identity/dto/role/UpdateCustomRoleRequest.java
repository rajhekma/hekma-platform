package com.hekma.identity.dto.role;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.Set;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Payload to update an existing custom role")
public class UpdateCustomRoleRequest {

    @Size(max = 100, message = "Role name must not exceed 100 characters.")
    @Schema(description = "Updated role name", example = "Senior Clinical Research Associate")
    private String name;

    @Size(max = 255, message = "Description must not exceed 255 characters.")
    @Schema(description = "Updated role description", example = "Leads site monitoring visits")
    private String description;

    @Schema(description = "Active status flag")
    private Boolean isActive;

    @Schema(description = "New authority keys set. If provided, replaces all authorities in this role", example = "[\"patient:read\", \"patient:update\", \"patient:assign\"]")
    private Set<String> authorities;
}
