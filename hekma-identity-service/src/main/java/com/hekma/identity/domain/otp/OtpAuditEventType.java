package com.hekma.identity.domain.otp;

public enum OtpAuditEventType {
    GENERATION,
    RESEND,
    VERIFICATION_SUCCESS,
    VERIFICATION_FAILURE,
    EXPIRATION,
    LOCKOUT
}
