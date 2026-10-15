package com.hekma.ctms.security;

import java.util.Set;
import java.util.UUID;

public record CtmsPrincipal(
        UUID userId,
        String email,
        String role,
        UUID tenantId,
        String tenantPath,
        Set<String> authorities,
        Set<String> customRoles
) {
    public boolean isPlatformAdmin() {
        return "SYSTEM_ADMIN".equals(role) || "ADMIN".equals(role);
    }

    public boolean hasAuthority(String authority) {
        return isPlatformAdmin() || (authorities != null && authorities.contains(authority));
    }

    /**
     * Checks if a target record's tenant path falls within this caller's tenant subtree.
     */
    public boolean isWithinSubtree(String targetTenantPath) {
        if (isPlatformAdmin()) {
            return true;
        }
        if (tenantPath == null || targetTenantPath == null) {
            return false;
        }
        return targetTenantPath.startsWith(tenantPath);
    }
}
