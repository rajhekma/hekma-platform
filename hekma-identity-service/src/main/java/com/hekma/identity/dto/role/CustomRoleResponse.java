package com.hekma.identity.dto.role;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Details of a custom role definition")
public class CustomRoleResponse {

    @Schema(description = "Role unique ID", example = "c71a3d92-23c8-4796-9321-7299a919e912")
    private UUID id;

    @Schema(description = "Role name", example = "Clinical Research Associate")
    private String name;

    @Schema(description = "Alphanumeric role code", example = "CRA")
    private String code;

    @Schema(description = "Role description")
    private String description;

    @Schema(description = "Owning tenant ID (null for global platform roles)")
    private UUID tenantId;

    @Schema(description = "Owning tenant materialized path")
    private String tenantPath;

    @Schema(description = "True if this is an immutable system role")
    private boolean isSystem;

    @Schema(description = "True if the role is active for assignment")
    private boolean isActive;

    @Schema(description = "Bundled authority keys")
    private List<String> authorities;

    @Schema(description = "Total number of authorities bundled")
    private int totalAuthorities;

    @Schema(description = "Number of active users currently assigned this role")
    private long assignedUserCount;

    @Schema(description = "Creation timestamp")
    private Instant createdAt;

    @Schema(description = "Last update timestamp")
    private Instant updatedAt;
}
