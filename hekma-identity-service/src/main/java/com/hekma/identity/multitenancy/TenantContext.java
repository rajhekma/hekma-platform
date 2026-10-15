package com.hekma.identity.multitenancy;

import java.util.UUID;

public final class TenantContext {

    private static final ThreadLocal<UUID> CURRENT_TENANT = new ThreadLocal<>();
    private static final ThreadLocal<Boolean> SYSTEM_BYPASS = ThreadLocal.withInitial(() -> false);

    private TenantContext() {
    }

    public static void setTenantId(UUID tenantId) {
        CURRENT_TENANT.set(tenantId);
    }

    public static UUID getTenantId() {
        return CURRENT_TENANT.get();
    }

    public static void setSystemBypass(boolean bypass) {
        SYSTEM_BYPASS.set(bypass);
    }

    public static boolean isSystemBypass() {
        return Boolean.TRUE.equals(SYSTEM_BYPASS.get());
    }

    public static void clear() {
        CURRENT_TENANT.remove();
        SYSTEM_BYPASS.remove();
    }
}
