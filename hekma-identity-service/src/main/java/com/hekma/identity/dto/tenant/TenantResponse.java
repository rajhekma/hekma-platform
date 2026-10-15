package com.hekma.identity.dto.tenant;

import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Detailed tenant organization profile response")
public class TenantResponse {

    @Schema(description = "Internal unique tenant identifier (UUID)")
    private UUID id;

    @Schema(description = "Organization name")
    private String name;

    @Schema(description = "URL/domain slug")
    private String slug;

    @Schema(description = "Tenant category (SPONSOR, SITE, GENERAL)")
    private TenantType tenantType;

    @Schema(description = "Whether this is the platform default organization (Hekma)")
    private Boolean defaultTenant;

    @Schema(description = "Tenant lifecycle status (ACTIVE, SUSPENDED, INACTIVE)")
    private TenantStatus status;

    @Schema(description = "Subscription tier (STANDARD, ENTERPRISE, PILOT)")
    private String subscriptionTier;

    @Schema(description = "Administrative contact email")
    private String contactEmail;

    @Schema(description = "Administrative contact phone")
    private String contactPhone;

    @Schema(description = "Tenant settings JSON string")
    private String settings;

    @Schema(description = "Parent tenant ID (null for a top-level tenant)")
    private UUID parentTenantId;

    @Schema(description = "Materialized path of tenant IDs from the root to this tenant", example = "/c1f8e21a-3a21-4b45-9876-000000000002/")
    private String path;

    @Schema(description = "Depth in the tenant tree (0 = top-level)", example = "0")
    private Integer depth;

    @Schema(description = "Total registered user members within this tenant")
    private Long memberCount;

    @Schema(description = "Timestamp when the tenant was provisioned")
    private Instant createdAt;

    @Schema(description = "Timestamp when the tenant was last modified")
    private Instant updatedAt;

    @Schema(description = "Informational message regarding the operation")
    private String message;
}
