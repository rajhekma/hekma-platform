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
@Schema(description = "Replaces a SPONSOR/SITE user's authorities. Every added or removed authority must be held by the caller.")
public class UpdateAuthoritiesRequest {

    @NotNull(message = "authorities is required (use an empty list to remove all)")
    @Schema(description = "Complete new set of authority keys", example = "[\"tenant:read\",\"patient:read\",\"patient:create\"]")
    private List<String> authorities;

    @Schema(description = "Reason recorded in the audit log", example = "Promoted to study coordinator")
    private String reason;
}
