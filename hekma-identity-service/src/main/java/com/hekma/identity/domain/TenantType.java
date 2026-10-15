package com.hekma.identity.domain;

public enum TenantType {
    SPONSOR,
    SITE,
    GENERAL;

    /**
     * The role carried by staff users of a tenant of this type (a user's role always matches its tenant's type).
     *
     * @return {@link Role#SPONSOR} or {@link Role#SITE}; null for the GENERAL (default) tenant, which has no staff
     */
    public Role staffRole() {
        return switch (this) {
            case SPONSOR -> Role.SPONSOR;
            case SITE -> Role.SITE;
            case GENERAL -> null;
        };
    }
}
