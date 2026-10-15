package com.hekma.notification.channel.push;

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
public class PushChannelHandler implements NotificationChannelHandler {

    private final PushProvider pushProvider;

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.PUSH;
    }

    @Override
    public NotificationResult handle(ChannelDispatchContext context) {
        log.debug("Dispatching Push notification for logId={}", context.getLogId());
        return pushProvider.sendPush(
                context.getRecipient(),
                context.getTitle(),
                context.getContent(),
                context.getMetadata()
        );
    }
}
