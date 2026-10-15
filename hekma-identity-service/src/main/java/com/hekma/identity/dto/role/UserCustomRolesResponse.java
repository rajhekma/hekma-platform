package com.hekma.identity.dto.role;

import io.swagger.v3.oas.annotations.media.Schema;
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
@Schema(description = "Custom roles and inherited authorities assigned to a user")
public class UserCustomRolesResponse {

    @Schema(description = "User unique ID", example = "d141483c-b5b6-4f92-a0a1-35c4d5fe6aeb")
    private UUID userId;

    @Schema(description = "User email address", example = "investigator@site.com")
    private String userEmail;

    @Schema(description = "Assigned custom roles")
    private List<CustomRoleResponse> customRoles;

    @Schema(description = "Union of authorities inherited across all assigned custom roles")
    private List<String> inheritedAuthorities;
}
