package com.hekma.notification.channel.sms;

import com.hekma.notification.channel.ChannelDispatchContext;
import com.hekma.notification.channel.NotificationChannelHandler;
import com.hekma.notification.channel.NotificationResult;
import com.hekma.notification.domain.model.NotificationChannel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class SmsChannelHandler implements NotificationChannelHandler {

    private final SmsProvider smsProvider;

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.SMS;
    }

    @Override
    public NotificationResult handle(ChannelDispatchContext context) {
        log.debug("Dispatching SMS notification for logId={}", context.getLogId());
        String message = context.getContent();
        if (context.getTitle() != null && !context.getTitle().isBlank()) {
            message = context.getTitle() + ": " + message;
        }
        return smsProvider.sendSms(context.getRecipient(), message);
    }
}
