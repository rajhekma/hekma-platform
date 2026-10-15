package com.hekma.identity.security;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;

import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;

/**
 * The authenticated caller, resolved from a verified Firebase ID token and loaded from the database on every request.
 * Role, tenant and authorities always come from PostgreSQL, never from token claims or client-supplied headers.
 *
 * @param userId the caller's user ID
 * @param firebaseUid the caller's Firebase UID
 * @param email the caller's email (may be null for phone-only accounts)
 * @param role the caller's role
 * @param tenantId the caller's tenant ID (null for platform roles)
 * @param tenantPath the caller's tenant materialized path (null for platform roles)
 * @param authorities authorities held: all for platform administrators, the granted set for SPONSOR/SITE, none for patients
 * @param customRoles custom role codes assigned to the caller
 */
public record HekmaPrincipal(UUID userId, String firebaseUid, String email, Role role, UUID tenantId, String tenantPath,
                             Set<Authority> authorities, Set<String> customRoles) {

    public HekmaPrincipal {
        authorities = authorities == null || authorities.isEmpty()
                ? Set.of()
                : Set.copyOf(authorities);
        customRoles = customRoles == null || customRoles.isEmpty()
                ? Set.of()
                : Set.copyOf(customRoles);
    }

    /**
     * Principal whose authorities follow its role: platform administrators hold every authority, others none.
     */
    public HekmaPrincipal(UUID userId, String firebaseUid, String email, Role role, UUID tenantId, String tenantPath) {
        this(userId, firebaseUid, email, role, tenantId, tenantPath,
                role == Role.SYSTEM_ADMIN || role == Role.ADMIN ? EnumSet.allOf(Authority.class) : Set.of(), Set.of());
    }

    public HekmaPrincipal(UUID userId, String firebaseUid, String email, Role role, UUID tenantId, String tenantPath,
                          Set<Authority> authorities) {
        this(userId, firebaseUid, email, role, tenantId, tenantPath, authorities, Set.of());
    }

    public boolean isPlatformAdmin() {
        return role == Role.SYSTEM_ADMIN || role == Role.ADMIN;
    }

    public boolean isTenantStaff() {
        return role == Role.SPONSOR || role == Role.SITE;
    }

    public boolean has(Authority authority) {
        return isPlatformAdmin() || authorities.contains(authority);
    }

    public boolean hasCustomRole(String roleCode) {
        return customRoles != null && customRoles.contains(roleCode);
    }

    /**
     * True when the tenant is the caller's own tenant or one of its descendants, for tenant staff.
     * Platform administrators see every tenant; patients see no subtree.
     */
    public boolean canSeeTenant(TenantEntity tenant) {
        if (isPlatformAdmin()) {
            return true;
        }
        return isTenantStaff() && tenant != null && tenantPath != null
                && tenant.getPath() != null && tenant.getPath().startsWith(tenantPath);
    }
}
