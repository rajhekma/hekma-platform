package com.hekma.identity.dto.iam;

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
@Schema(description = "Authorities held by a user")
public class AuthoritiesResponse {

    private UUID userId;

    @Schema(description = "Authority keys", example = "[\"patient:create\",\"patient:read\",\"tenant:read\"]")
    private List<String> authorities;
}
