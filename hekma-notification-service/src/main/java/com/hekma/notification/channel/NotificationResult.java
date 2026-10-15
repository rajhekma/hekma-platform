package com.hekma.notification.channel;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class NotificationResult {
    private final boolean success;
    private final String providerMessageId;
    private final String errorMessage;

    public static NotificationResult success(String providerMessageId) {
        return NotificationResult.builder()
                .success(true)
                .providerMessageId(providerMessageId)
                .build();
    }

    public static NotificationResult failure(String errorMessage) {
        return NotificationResult.builder()
                .success(false)
                .errorMessage(errorMessage)
                .build();
    }
}
