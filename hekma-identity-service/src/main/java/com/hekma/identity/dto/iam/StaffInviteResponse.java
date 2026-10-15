package com.hekma.identity.dto.iam;

import com.hekma.identity.domain.Role;
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
@Schema(description = "Created staff invitation. The single-use token is sent only to the invitee's email.")
public class StaffInviteResponse {

    private UUID invitationId;
    private String email;
    private Role role;
    private UUID tenantId;
    private String tenantSlug;
    private List<String> authorities;
    private Instant expiresAt;
    private String message;
}
