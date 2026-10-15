package com.hekma.appointment.service;

import com.hekma.appointment.domain.ViewedStatus;
import com.hekma.appointment.domain.WebNotificationEntity;
import com.hekma.appointment.dto.ReminderDto;
import com.hekma.appointment.exception.ResourceNotFoundException;
import com.hekma.appointment.repository.WebNotificationRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class WebNotificationService {

    private final WebNotificationRepository repository;

    @Transactional(readOnly = true)
    public List<ReminderDto> getReminders(String userId, String userType) {
        return repository.findByUserIdAndUserTypeOrderByCreatedAtDesc(userId, userType).stream()
                .map(ReminderDto::fromEntity)
                .toList();
    }

    @Transactional
    public void createReminder(String userId, String userType, String referenceId, String referenceType,
                               Instant referenceTimestamp, String notificationType, String message) {
        WebNotificationEntity entity = WebNotificationEntity.builder()
                .userId(userId)
                .userType(userType)
                .referenceId(referenceId)
                .referenceType(referenceType)
                .referenceTimestamp(referenceTimestamp)
                .notificationType(notificationType)
                .message(message)
                .viewedStatus(ViewedStatus.UNREAD)
                .build();
        repository.save(entity);
    }

    @Transactional
    public void markViewed(UUID id) {
        WebNotificationEntity entity = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Web notification not found with id: " + id));
        entity.setViewedStatus(ViewedStatus.READ);
        repository.save(entity);
    }

    @Transactional
    public void deleteRemindersForReference(String referenceId, String notificationType) {
        repository.deleteByReferenceIdAndNotificationType(referenceId, notificationType);
    }
}
