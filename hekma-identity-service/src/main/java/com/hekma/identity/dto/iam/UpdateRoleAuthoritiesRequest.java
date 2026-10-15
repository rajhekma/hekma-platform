package com.hekma.identity.dto.iam;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
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
@Schema(description = "Payload to update default authorities for a configurable role")
public class UpdateRoleAuthoritiesRequest {

    @NotNull(message = "authorities is required (use an empty list to remove all)")
    @Schema(description = "Complete new set of authority keys for the role", example = "[\"tenant:read\",\"patient:read\"]")
    private List<String> authorities;

    @Schema(description = "If true, cascades authority changes to all active existing users of this role. If false, only new users receive these defaults.", defaultValue = "false")
    private Boolean applyToExistingUsers;

    @Schema(description = "Reason recorded in the audit log", example = "Updated default site privileges")
    private String reason;
}
