package com.hekma.identity.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;

import java.util.UUID;

@Entity
@Table(name = "identity_tenants")
@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@AllArgsConstructor
@EqualsAndHashCode(onlyExplicitlyIncluded = true, callSuper = false)
public class TenantEntity extends BaseAuditEntity {

    /**
     * Assigned by the application (see {@link #assignIdAndPath()}) so that the materialized path,
     * which contains the tenant's own ID, can be computed before the row is inserted.
     */
    @Id
    @EqualsAndHashCode.Include
    private UUID id;

    /**
     * Parent tenant; null for a top-level tenant.
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "parent_tenant_id")
    private TenantEntity parent;

    /**
     * Materialized path of tenant IDs from the root to this tenant, e.g. {@code /<root-id>/<child-id>/}.
     * A tenant's subtree is every tenant whose path starts with this path.
     */
    @Column(name = "path", nullable = false, length = 2048, updatable = false)
    private String path;

    /**
     * Depth in the tenant tree: 0 for a top-level tenant.
     */
    @Column(name = "depth", nullable = false, updatable = false)
    @Builder.Default
    private int depth = 0;

    @Column(name = "name", nullable = false, length = 255)
    private String name;

    @Column(name = "slug", nullable = false, unique = true, length = 100)
    private String slug;

    @Enumerated(EnumType.STRING)
    @Column(name = "tenant_type", nullable = false, length = 50)
    @Builder.Default
    private TenantType tenantType = TenantType.GENERAL;

    @Column(name = "default_tenant", nullable = false)
    @Builder.Default
    private boolean defaultTenant = false;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 50)
    @Builder.Default
    private TenantStatus status = TenantStatus.ACTIVE;

    @Column(name = "subscription_tier", length = 50)
    @Builder.Default
    private String subscriptionTier = "STANDARD";

    @Column(name = "contact_email", length = 255)
    private String contactEmail;

    @Column(name = "contact_phone", length = 50)
    private String contactPhone;

    @Column(name = "settings", columnDefinition = "TEXT")
    private String settings;

    @PrePersist
    void assignIdAndPath() {
        if (id == null) {
            id = UUID.randomUUID();
        }
        if (path == null) {
            path = (parent != null ? parent.getPath() : "/") + id + "/";
            depth = parent != null ? parent.getDepth() + 1 : 0;
        }
    }

    /**
     * Returns true when the given tenant is this tenant or one of its descendants.
     */
    public boolean containsInSubtree(TenantEntity other) {
        return other != null && path != null && other.getPath() != null && other.getPath().startsWith(path);
    }

    public boolean isDefaultTenant() {
        return defaultTenant;
    }

    public boolean getDefaultTenant() {
        return defaultTenant;
    }
}
