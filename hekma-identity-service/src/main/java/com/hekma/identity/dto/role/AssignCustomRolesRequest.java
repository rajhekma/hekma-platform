package com.hekma.identity.dto.role;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
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
@Schema(description = "Payload to assign custom roles to a user")
public class AssignCustomRolesRequest {

    @NotNull(message = "Role IDs set cannot be null.")
    @Schema(description = "Set of custom role UUIDs to assign", example = "[\"c71a3d92-23c8-4796-9321-7299a919e912\"]")
    private Set<UUID> roleIds;

    @Schema(description = "Reason for role assignment (recorded in audit log)", example = "Assigned as Clinical Trial Monitor")
    private String reason;
}
