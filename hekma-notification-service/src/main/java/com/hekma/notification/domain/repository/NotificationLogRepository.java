package com.hekma.notification.domain.repository;

import com.hekma.notification.domain.entity.NotificationLog;
import com.hekma.notification.domain.model.NotificationChannel;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface NotificationLogRepository extends JpaRepository<NotificationLog, UUID> {

    Optional<NotificationLog> findByIdempotencyKey(String idempotencyKey);

    Page<NotificationLog> findByRecipient(String recipient, Pageable pageable);

    Page<NotificationLog> findByChannel(NotificationChannel channel, Pageable pageable);
}
