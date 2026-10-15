package com.hekma.notification.service;

import com.hekma.notification.domain.entity.InAppNotification;
import com.hekma.notification.domain.repository.InAppNotificationRepository;
import com.hekma.notification.dto.InAppNotificationDto;
import com.hekma.notification.dto.UnreadCountDto;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.NoSuchElementException;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class InAppNotificationService {

    private final InAppNotificationRepository inAppRepository;

    @Transactional(readOnly = true)
    public Page<InAppNotificationDto> getUserNotifications(String userId, Boolean unreadOnly, Pageable pageable) {
        Page<InAppNotification> page;
        if (Boolean.TRUE.equals(unreadOnly)) {
            page = inAppRepository.findByUserIdAndIsReadOrderByCreatedAtDesc(userId, false, pageable);
        } else {
            page = inAppRepository.findByUserIdOrderByCreatedAtDesc(userId, pageable);
        }
        return page.map(this::toDto);
    }

    @Transactional(readOnly = true)
    public UnreadCountDto getUnreadCount(String userId) {
        long count = inAppRepository.countByUserIdAndIsReadFalse(userId);
        return UnreadCountDto.builder()
                .userId(userId)
                .unreadCount(count)
                .build();
    }

    @Transactional
    public InAppNotificationDto markAsRead(UUID id) {
        InAppNotification notification = inAppRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("Notification not found with ID: " + id));

        notification.markAsRead();
        InAppNotification saved = inAppRepository.save(notification);
        log.info("Marked notification {} as read for user {}", id, saved.getUserId());
        return toDto(saved);
    }

    @Transactional
    public int markAllAsRead(String userId) {
        int updated = inAppRepository.markAllAsReadByUserId(userId, Instant.now());
        log.info("Marked {} notifications as read for user {}", updated, userId);
        return updated;
    }

    @Transactional
    public void deleteNotification(UUID id) {
        if (!inAppRepository.existsById(id)) {
            throw new NoSuchElementException("Notification not found with ID: " + id);
        }
        inAppRepository.deleteById(id);
        log.info("Deleted in-app notification with ID: {}", id);
    }

    private InAppNotificationDto toDto(InAppNotification entity) {
        return InAppNotificationDto.builder()
                .id(entity.getId())
                .userId(entity.getUserId())
                .title(entity.getTitle())
                .content(entity.getContent())
                .category(entity.getCategory())
                .actionUrl(entity.getActionUrl())
                .dataJson(entity.getDataJson())
                .isRead(entity.isRead())
                .readAt(entity.getReadAt())
                .createdAt(entity.getCreatedAt())
                .build();
    }
}
