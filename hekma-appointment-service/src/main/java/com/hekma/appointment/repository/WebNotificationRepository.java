package com.hekma.appointment.repository;

import com.hekma.appointment.domain.ViewedStatus;
import com.hekma.appointment.domain.WebNotificationEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface WebNotificationRepository extends JpaRepository<WebNotificationEntity, UUID> {

    List<WebNotificationEntity> findByUserIdAndUserTypeOrderByCreatedAtDesc(String userId, String userType);

    List<WebNotificationEntity> findByUserIdAndUserTypeAndViewedStatusOrderByCreatedAtDesc(String userId, String userType, ViewedStatus viewedStatus);

    void deleteByReferenceIdAndNotificationType(String referenceId, String notificationType);
}
