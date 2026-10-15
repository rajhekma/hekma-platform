package com.hekma.identity.multitenancy;

import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.repository.TenantRepository;

import java.util.Arrays;
import java.util.List;
import java.util.UUID;

/**
 * Helpers for the materialized tenant path ({@code /<root-id>/<child-id>/}).
 */
public final class TenantPaths {

    private TenantPaths() {
    }

    /**
     * Tenant IDs on a path, root first, including the tenant itself.
     */
    public static List<UUID> ids(String path) {
        if (path == null || path.isBlank()) {
            return List.of();
        }
        return Arrays.stream(path.split("/"))
                .filter(part -> !part.isBlank())
                .map(UUID::fromString)
                .toList();
    }

    /**
     * True when the tenant and all of its ancestors are ACTIVE. A suspended, inactive or unverified
     * ancestor blocks every tenant below it.
     */
    public static boolean isChainActive(TenantEntity tenant, TenantRepository tenantRepository) {
        if (tenant == null) {
            return true;
        }
        if (tenant.getStatus() != TenantStatus.ACTIVE) {
            return false;
        }
        List<UUID> ancestors = ids(tenant.getPath());
        return ancestors.size() <= 1 || !tenantRepository.existsByIdInAndStatusNot(ancestors, TenantStatus.ACTIVE);
    }
}
