package com.hekma.identity.exception;

public class TenantSuspendedException extends RuntimeException {
    public TenantSuspendedException(String message) {
        super(message);
    }
}
