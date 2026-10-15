package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportSlaInfoDto {
    private Integer slaHours;
    private String dueAt;
    private String firstResponseAt;
    private String resolvedAt;
    private Boolean breached;
    private Integer remainingMinutes;
    private String expectedResponseText;
}
