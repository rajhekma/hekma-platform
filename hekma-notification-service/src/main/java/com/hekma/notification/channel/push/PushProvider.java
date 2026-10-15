package com.hekma.notification.channel.push;

import com.hekma.notification.channel.NotificationResult;

import java.util.Map;

public interface PushProvider {
    NotificationResult sendPush(String token, String title, String body, Map<String, Object> data);
}
