package com.hekma.appointment.service;

import com.hekma.appointment.domain.NotificationPreferenceEntity;
import com.hekma.appointment.dto.NotificationPreferenceDto;
import com.hekma.appointment.repository.NotificationPreferenceRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Slf4j
public class NotificationPreferenceService {

    private final NotificationPreferenceRepository repository;

    @Transactional(readOnly = true)
    public NotificationPreferenceDto getPreference(String userId, String userType) {
        return repository.findByUserIdAndUserType(userId, userType)
                .map(NotificationPreferenceDto::fromEntity)
                .orElseGet(() -> NotificationPreferenceDto.builder()
                        .userId(userId)
                        .userType(userType)
                        .toggleInApp(true)
                        .toggleEmail(true)
                        .toggleMessage(false)
                        .build());
    }

    @Transactional
    public NotificationPreferenceDto updatePreference(String userId, String userType, Boolean toggleInApp, Boolean toggleEmail, Boolean toggleMessage) {
        NotificationPreferenceEntity entity = repository.findByUserIdAndUserType(userId, userType)
                .orElseGet(() -> NotificationPreferenceEntity.builder()
                        .userId(userId)
                        .userType(userType)
                        .toggleInApp(true)
                        .toggleEmail(true)
                        .toggleMessage(false)
                        .build());

        if (toggleInApp != null) {
            entity.setToggleInApp(toggleInApp);
        }
        if (toggleEmail != null) {
            entity.setToggleEmail(toggleEmail);
        }
        if (toggleMessage != null) {
            entity.setToggleMessage(toggleMessage);
        }

        NotificationPreferenceEntity saved = repository.save(entity);
        log.info("Updated notification preferences for user {} ({})", userId, userType);
        return NotificationPreferenceDto.fromEntity(saved);
    }

    @Transactional(readOnly = true)
    public boolean isNotificationEnabled(String userId, String userType, String channel) {
        NotificationPreferenceDto pref = getPreference(userId, userType);
        if ("EMAIL".equalsIgnoreCase(channel)) {
            return Boolean.TRUE.equals(pref.getToggleEmail());
        }
        if ("IN_APP".equalsIgnoreCase(channel) || "PUSH".equalsIgnoreCase(channel)) {
            return Boolean.TRUE.equals(pref.getToggleInApp());
        }
        if ("SMS".equalsIgnoreCase(channel)) {
            return Boolean.TRUE.equals(pref.getToggleMessage());
        }
        return true;
    }
}
