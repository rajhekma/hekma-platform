package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportOtpVerifyResultDto {
    private Boolean success;
    private String otpToken;
    private String email;
    private Integer expiresIn;
    private String message;
}
