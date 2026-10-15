package com.hekma.notification.channel.inapp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.notification.channel.ChannelDispatchContext;
import com.hekma.notification.channel.NotificationChannelHandler;
import com.hekma.notification.channel.NotificationResult;
import com.hekma.notification.domain.entity.InAppNotification;
import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.repository.InAppNotificationRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class InAppChannelHandler implements NotificationChannelHandler {

    private final InAppNotificationRepository inAppNotificationRepository;
    private final ObjectMapper objectMapper;

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.IN_APP;
    }

    @Override
    public NotificationResult handle(ChannelDispatchContext context) {
        log.debug("Dispatching In-App notification for user={}", context.getRecipient());
        try {
            String category = "GENERAL";
            String actionUrl = null;
            String dataJson = null;

            Map<String, Object> metadata = context.getMetadata();
            if (metadata != null) {
                if (metadata.containsKey("category")) {
                    category = String.valueOf(metadata.get("category"));
                }
                if (metadata.containsKey("actionUrl")) {
                    actionUrl = String.valueOf(metadata.get("actionUrl"));
                }
                dataJson = objectMapper.writeValueAsString(metadata);
            }

            InAppNotification notification = InAppNotification.builder()
                    .userId(context.getRecipient())
                    .title(context.getTitle() != null ? context.getTitle() : "Notification")
                    .content(context.getContent())
                    .category(category)
                    .actionUrl(actionUrl)
                    .dataJson(dataJson)
                    .isRead(false)
                    .build();

            InAppNotification saved = inAppNotificationRepository.save(notification);
            log.info("In-App notification saved for user={} with ID={}", saved.getUserId(), saved.getId());
            return NotificationResult.success(saved.getId().toString());
        } catch (Exception ex) {
            log.error("Failed to save In-App notification: {}", ex.getMessage(), ex);
            return NotificationResult.failure("In-App persistence failed: " + ex.getMessage());
        }
    }
}
