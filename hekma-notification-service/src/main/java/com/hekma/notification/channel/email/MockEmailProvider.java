package com.hekma.notification.channel.email;

import com.hekma.notification.channel.NotificationResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.notification.channels.email.provider", havingValue = "mock", matchIfMissing = true)
public class MockEmailProvider implements EmailProvider {

    @Override
    public NotificationResult sendEmail(String to, String subject, String body, String from) {
        String messageId = "mock-email-" + UUID.randomUUID();
        log.info("[MOCK EMAIL DISPATCHED] ID: {} | From: {} | To: {} | Subject: {} | Content: {}",
                messageId, from, to, subject, body);
        return NotificationResult.success(messageId);
    }
}
