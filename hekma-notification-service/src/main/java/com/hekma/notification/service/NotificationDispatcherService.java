package com.hekma.notification.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.notification.channel.ChannelDispatchContext;
import com.hekma.notification.channel.NotificationChannelHandler;
import com.hekma.notification.channel.NotificationChannelRegistry;
import com.hekma.notification.channel.NotificationResult;
import com.hekma.notification.domain.entity.NotificationLog;
import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationStatus;
import com.hekma.notification.domain.repository.NotificationLogRepository;
import com.hekma.notification.dto.BroadcastNotificationRequest;
import com.hekma.notification.dto.BroadcastNotificationResponse;
import com.hekma.notification.dto.NotificationResponse;
import com.hekma.notification.dto.NotificationSendRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class NotificationDispatcherService {

    private final NotificationChannelRegistry channelRegistry;
    private final NotificationLogRepository notificationLogRepository;
    private final NotificationAsyncDispatcher asyncDispatcher;
    private final TemplateRenderer templateRenderer;
    private final ObjectMapper objectMapper;

    @Transactional
    public NotificationResponse sendNotification(NotificationSendRequest request) {
        // Idempotency check
        if (request.getIdempotencyKey() != null && !request.getIdempotencyKey().isBlank()) {
            Optional<NotificationLog> existingLog = notificationLogRepository.findByIdempotencyKey(request.getIdempotencyKey());
            if (existingLog.isPresent()) {
                log.info("Idempotent request detected for key={}. Returning existing log ID={}",
                        request.getIdempotencyKey(), existingLog.get().getId());
                return toResponse(existingLog.get(), null);
            }
        }

        NotificationChannel channel = request.getChannel();
        NotificationChannelHandler handler = channelRegistry.getHandler(channel)
                .orElseThrow(() -> new IllegalArgumentException("No handler registered for channel: " + channel));

        // Render template placeholders if templateParams are provided
        String title = templateRenderer.render(request.getTitle(), request.getTemplateParams());
        String content = templateRenderer.render(request.getContent(), request.getTemplateParams());

        String metadataJson = null;
        if (request.getMetadata() != null) {
            try {
                metadataJson = objectMapper.writeValueAsString(request.getMetadata());
            } catch (JsonProcessingException e) {
                log.warn("Failed to serialize metadata to JSON: {}", e.getMessage());
            }
        }

        NotificationLog logEntry = NotificationLog.builder()
                .channel(channel)
                .recipient(request.getRecipient())
                .title(title)
                .content(content)
                .priority(request.getPriority())
                .sourceService(request.getSourceService())
                .idempotencyKey(request.getIdempotencyKey())
                .metadataJson(metadataJson)
                .status(NotificationStatus.PENDING)
                .build();

        NotificationLog savedLog = notificationLogRepository.save(logEntry);

        ChannelDispatchContext context = ChannelDispatchContext.builder()
                .logId(savedLog.getId())
                .channel(channel)
                .recipient(request.getRecipient())
                .title(title)
                .content(content)
                .priority(request.getPriority())
                .sourceService(request.getSourceService())
                .metadata(request.getMetadata())
                .build();

        boolean isAsync = request.getAsync() == null || Boolean.TRUE.equals(request.getAsync());

        if (isAsync) {
            asyncDispatcher.dispatchAsync(handler, context, savedLog.getId());
            return toResponse(savedLog, null);
        } else {
            // Synchronous execution
            try {
                NotificationResult result = handler.handle(context);
                if (result.isSuccess()) {
                    savedLog.setStatus(NotificationStatus.SENT);
                } else {
                    savedLog.setStatus(NotificationStatus.FAILED);
                    savedLog.setErrorMessage(result.getErrorMessage());
                }
                notificationLogRepository.save(savedLog);
                return toResponse(savedLog, result.getProviderMessageId());
            } catch (Exception ex) {
                log.error("Sync dispatch failed: {}", ex.getMessage(), ex);
                savedLog.setStatus(NotificationStatus.FAILED);
                savedLog.setErrorMessage(ex.getMessage());
                notificationLogRepository.save(savedLog);
                return toResponse(savedLog, null);
            }
        }
    }

    public BroadcastNotificationResponse broadcast(BroadcastNotificationRequest request) {
        List<NotificationResponse> results = new ArrayList<>();

        for (NotificationChannel channel : request.getChannels()) {
            String recipient = resolveRecipient(channel, request);
            if (recipient == null || recipient.isBlank()) {
                results.add(NotificationResponse.builder()
                        .channel(channel)
                        .recipient("MISSING")
                        .status(NotificationStatus.FAILED)
                        .errorMessage("Recipient identifier missing for channel: " + channel)
                        .build());
                continue;
            }

            NotificationSendRequest sendRequest = NotificationSendRequest.builder()
                    .channel(channel)
                    .recipient(recipient)
                    .title(request.getTitle())
                    .content(request.getContent())
                    .priority(request.getPriority())
                    .sourceService(request.getSourceService())
                    .metadata(request.getMetadata())
                    .async(true)
                    .build();

            try {
                NotificationResponse response = sendNotification(sendRequest);
                results.add(response);
            } catch (Exception ex) {
                log.error("Error broadcasting to channel {}: {}", channel, ex.getMessage(), ex);
                results.add(NotificationResponse.builder()
                        .channel(channel)
                        .recipient(recipient)
                        .status(NotificationStatus.FAILED)
                        .errorMessage(ex.getMessage())
                        .build());
            }
        }

        return BroadcastNotificationResponse.builder()
                .totalDispatched(results.size())
                .results(results)
                .build();
    }

    @Transactional(readOnly = true)
    public NotificationResponse getStatus(UUID id) {
        NotificationLog logEntry = notificationLogRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("Notification log not found with ID: " + id));
        return toResponse(logEntry, null);
    }

    private String resolveRecipient(NotificationChannel channel, BroadcastNotificationRequest request) {
        return switch (channel) {
            case EMAIL -> request.getEmail();
            case SMS -> request.getPhone();
            case PUSH -> request.getPushToken();
            case IN_APP -> request.getUserId();
        };
    }

    private NotificationResponse toResponse(NotificationLog entity, String providerMessageId) {
        return NotificationResponse.builder()
                .id(entity.getId())
                .channel(entity.getChannel())
                .recipient(entity.getRecipient())
                .status(entity.getStatus())
                .providerMessageId(providerMessageId)
                .errorMessage(entity.getErrorMessage())
                .createdAt(entity.getCreatedAt())
                .build();
    }
}
