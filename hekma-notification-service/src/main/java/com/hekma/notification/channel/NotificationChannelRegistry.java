package com.hekma.notification.channel;

import com.hekma.notification.domain.model.NotificationChannel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Slf4j
@Component
public class NotificationChannelRegistry {

    private final Map<NotificationChannel, NotificationChannelHandler> handlers = new EnumMap<>(NotificationChannel.class);

    public NotificationChannelRegistry(List<NotificationChannelHandler> channelHandlers) {
        for (NotificationChannelHandler handler : channelHandlers) {
            handlers.put(handler.getChannel(), handler);
            log.info("Registered channel handler: [{}] -> {}", handler.getChannel(), handler.getClass().getSimpleName());
        }
    }

    public Optional<NotificationChannelHandler> getHandler(NotificationChannel channel) {
        return Optional.ofNullable(handlers.get(channel));
    }

    public boolean hasHandler(NotificationChannel channel) {
        return handlers.containsKey(channel);
    }
}
