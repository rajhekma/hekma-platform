package com.hekma.identity.domain.otp;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Mode used for user authentication and OTP verification (PHONE, EMAIL)")
public enum VerificationMode {
    PHONE,
    EMAIL
}
