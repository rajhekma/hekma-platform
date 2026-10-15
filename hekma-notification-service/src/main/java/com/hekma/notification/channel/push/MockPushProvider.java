package com.hekma.notification.channel.push;

import com.hekma.notification.channel.NotificationResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.UUID;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.notification.channels.push.provider", havingValue = "mock", matchIfMissing = true)
public class MockPushProvider implements PushProvider {

    @Override
    public NotificationResult sendPush(String token, String title, String body, Map<String, Object> data) {
        String messageId = "mock-push-" + UUID.randomUUID();
        log.info("[MOCK PUSH DISPATCHED] ID: {} | DeviceToken: {} | Title: {} | Body: {} | Data: {}",
                messageId, token, title, body, data);
        return NotificationResult.success(messageId);
    }
}
