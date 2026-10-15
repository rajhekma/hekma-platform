package com.hekma.identity.exception;

public class OtpVerificationLimitException extends RuntimeException {

    public OtpVerificationLimitException(String message) {
        super(message);
    }
}
