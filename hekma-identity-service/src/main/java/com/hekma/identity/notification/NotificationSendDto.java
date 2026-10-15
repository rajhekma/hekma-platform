package com.hekma.identity.notification;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class NotificationSendDto {
    private String channel;
    private String recipient;
    private String title;
    private String content;
    private String priority;
    private Map<String, Object> templateParams;
    private String sourceService;
    private String idempotencyKey;
    private Boolean async;
}
