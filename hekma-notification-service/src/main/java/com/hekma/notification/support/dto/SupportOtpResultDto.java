package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportOtpResultDto {
    private Boolean success;
    private String challengeId;
    private String maskedEmail;
    private Integer expiry;
    private Integer retryAfter;
    private String message;
}
