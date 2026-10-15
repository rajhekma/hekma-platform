package com.hekma.identity.exception;

public class CustomRoleNotFoundException extends RuntimeException {
    public CustomRoleNotFoundException(String message) {
        super(message);
    }
}
