package com.hekma.notification.channel.email;

import com.hekma.notification.channel.ChannelDispatchContext;
import com.hekma.notification.channel.NotificationChannelHandler;
import com.hekma.notification.channel.NotificationResult;
import com.hekma.notification.domain.model.NotificationChannel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class EmailChannelHandler implements NotificationChannelHandler {

    private final EmailProvider emailProvider;
    private final String defaultSender;

    public EmailChannelHandler(EmailProvider emailProvider,
                               @Value("${hekma.notification.channels.email.default-sender:no-reply@hekma.com}") String defaultSender) {
        this.emailProvider = emailProvider;
        this.defaultSender = defaultSender;
    }

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.EMAIL;
    }

    @Override
    public NotificationResult handle(ChannelDispatchContext context) {
        log.debug("Dispatching email notification for logId={}", context.getLogId());
        return emailProvider.sendEmail(
                context.getRecipient(),
                context.getTitle(),
                context.getContent(),
                defaultSender
        );
    }
}
