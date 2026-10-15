package com.hekma.notification.service;

import com.hekma.notification.channel.ChannelDispatchContext;
import com.hekma.notification.channel.NotificationChannelHandler;
import com.hekma.notification.channel.NotificationResult;
import com.hekma.notification.domain.entity.NotificationLog;
import com.hekma.notification.domain.model.NotificationStatus;
import com.hekma.notification.domain.repository.NotificationLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class NotificationAsyncDispatcher {

    private final NotificationLogRepository notificationLogRepository;

    @Async("notificationTaskExecutor")
    public void dispatchAsync(NotificationChannelHandler handler, ChannelDispatchContext context, UUID logId) {
        log.debug("Executing async dispatch for logId={}", logId);
        try {
            NotificationResult result = handler.handle(context);
            updateLogStatus(logId, result);
        } catch (Exception ex) {
            log.error("Unhandled exception during async dispatch for logId={}: {}", logId, ex.getMessage(), ex);
            updateLogStatus(logId, NotificationResult.failure("Unexpected failure: " + ex.getMessage()));
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateLogStatus(UUID logId, NotificationResult result) {
        notificationLogRepository.findById(logId).ifPresent(logEntry -> {
            if (result.isSuccess()) {
                logEntry.setStatus(NotificationStatus.SENT);
                log.info("Notification logId={} successfully sent", logId);
            } else {
                logEntry.setStatus(NotificationStatus.FAILED);
                logEntry.setErrorMessage(result.getErrorMessage());
                log.warn("Notification logId={} failed: {}", logId, result.getErrorMessage());
            }
            notificationLogRepository.save(logEntry);
        });
    }
}
