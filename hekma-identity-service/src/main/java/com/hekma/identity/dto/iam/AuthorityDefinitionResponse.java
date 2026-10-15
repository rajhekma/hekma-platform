package com.hekma.identity.dto.iam;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Definition and metadata for a platform authority")
public class AuthorityDefinitionResponse {

    @Schema(description = "Authority key", example = "tenant:read")
    private String key;

    @Schema(description = "Human-readable authority name", example = "View Tenant Hierarchy")
    private String name;

    @Schema(description = "Functional group/category", example = "Tenant Governance")
    private String category;

    @Schema(description = "Description of capability", example = "View own tenant and descendant tenants")
    private String description;

    @Schema(description = "Allowed roles permitted to hold this authority", example = "[\"ADMIN\",\"SPONSOR\",\"SITE\"]")
    private List<String> allowedRoles;
}
