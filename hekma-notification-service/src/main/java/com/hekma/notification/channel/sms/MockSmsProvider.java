package com.hekma.notification.channel.sms;

import com.hekma.notification.channel.NotificationResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.notification.channels.sms.provider", havingValue = "mock", matchIfMissing = true)
public class MockSmsProvider implements SmsProvider {

    @Override
    public NotificationResult sendSms(String phoneNumber, String message) {
        String messageId = "mock-sms-" + UUID.randomUUID();
        log.info("[MOCK SMS DISPATCHED] ID: {} | To: {} | Message: {}",
                messageId, phoneNumber, message);
        return NotificationResult.success(messageId);
    }
}
