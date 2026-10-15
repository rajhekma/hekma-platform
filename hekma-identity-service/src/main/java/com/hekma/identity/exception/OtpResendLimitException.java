package com.hekma.identity.exception;

public class OtpResendLimitException extends RuntimeException {

    public OtpResendLimitException(String message) {
        super(message);
    }
}
