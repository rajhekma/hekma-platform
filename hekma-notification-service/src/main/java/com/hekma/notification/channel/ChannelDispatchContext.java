package com.hekma.notification.channel;

import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationPriority;
import lombok.Builder;
import lombok.Getter;

import java.util.Map;
import java.util.UUID;

@Getter
@Builder
public class ChannelDispatchContext {
    private final UUID logId;
    private final NotificationChannel channel;
    private final String recipient;
    private final String title;
    private final String content;
    private final NotificationPriority priority;
    private final String sourceService;
    private final Map<String, Object> metadata;
}
