package com.hekma.identity.domain;

public enum Role {
    SYSTEM_ADMIN,
    ADMIN,
    SPONSOR,
    SITE,
    PATIENT;

    /**
     * Determines whether users can self-register with this role through the public registration API.
     * Only PATIENT is allowed. SYSTEM_ADMIN is pre-seeded, ADMIN is created by SYSTEM_ADMIN, and
     * SPONSOR/SITE accounts are created through tenant registration or invitation.
     */
    public boolean isPubliclyRegisterable() {
        return this == PATIENT;
    }
}
