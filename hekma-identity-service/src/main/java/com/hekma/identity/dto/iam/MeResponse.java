package com.hekma.identity.dto.iam;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserStatus;
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
@Schema(description = "The authenticated caller: profile, tenant position and effective authorities (for rendering the UI)")
public class MeResponse {

    private UUID userId;
    private String email;
    private String phoneNumber;
    private String displayName;
    private Role role;
    private UserStatus status;
    private boolean twoFactorEnabled;

    private UUID tenantId;
    private String tenantName;
    private String tenantSlug;
    private TenantType tenantType;
    @Schema(description = "Materialized tenant path; the caller's scope is every tenant whose path starts with it")
    private String tenantPath;

    @Schema(description = "Effective authority keys (all for platform administrators, none for patients)")
    private List<String> authorities;

    @Schema(description = "Assigned custom role codes")
    private List<String> customRoles;
}
