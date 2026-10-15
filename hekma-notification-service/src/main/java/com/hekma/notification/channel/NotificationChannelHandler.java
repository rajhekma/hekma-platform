package com.hekma.notification.channel;

import com.hekma.notification.domain.model.NotificationChannel;

public interface NotificationChannelHandler {
    NotificationChannel getChannel();
    NotificationResult handle(ChannelDispatchContext context);
}
