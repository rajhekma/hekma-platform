package com.hekma.identity.exception;

import lombok.Getter;

import java.time.Instant;

@Getter
public class OtpLockoutException extends RuntimeException {

    private final Instant lockedUntil;

    public OtpLockoutException(String message) {
        super(message);
        this.lockedUntil = null;
    }

    public OtpLockoutException(String message, Instant lockedUntil) {
        super(message);
        this.lockedUntil = lockedUntil;
    }
}
