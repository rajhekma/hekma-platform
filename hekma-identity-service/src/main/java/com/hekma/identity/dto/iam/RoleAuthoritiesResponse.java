package com.hekma.identity.dto.iam;

import com.hekma.identity.domain.Role;
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
@Schema(description = "Default authorities assigned to a configurable role")
public class RoleAuthoritiesResponse {

    @Schema(description = "Platform role", example = "SPONSOR")
    private Role role;

    @Schema(description = "Authority keys", example = "[\"tenant:read\",\"patient:read\"]")
    private List<String> authorities;

    @Schema(description = "Count of assigned authorities", example = "12")
    private int totalAuthorities;
}
