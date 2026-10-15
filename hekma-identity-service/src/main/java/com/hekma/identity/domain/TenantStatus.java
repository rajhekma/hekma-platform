package com.hekma.identity.domain;

public enum TenantStatus {
    /**
     * Self-registered tenant awaiting the owner's OTP verification. Its users cannot sign in.
     */
    PENDING_VERIFICATION,
    ACTIVE,
    SUSPENDED,
    INACTIVE
}
