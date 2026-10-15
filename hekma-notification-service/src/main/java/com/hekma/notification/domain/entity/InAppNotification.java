package com.hekma.notification.domain.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "notification_in_app_notifications", indexes = {
        @Index(name = "notification_idx_in_app_user_id", columnList = "user_id"),
        @Index(name = "notification_idx_in_app_is_read", columnList = "user_id, is_read"),
        @Index(name = "notification_idx_in_app_created_at", columnList = "created_at")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class InAppNotification {

    @Id
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @Column(name = "user_id", length = 100, nullable = false)
    private String userId;

    @Column(name = "title", nullable = false)
    private String title;

    @Column(name = "content", columnDefinition = "TEXT", nullable = false)
    private String content;

    @Column(name = "category", length = 50)
    @Builder.Default
    private String category = "GENERAL";

    @Column(name = "action_url", length = 500)
    private String actionUrl;

    @Column(name = "data_json", columnDefinition = "TEXT")
    private String dataJson;

    @Column(name = "is_read", nullable = false)
    @Builder.Default
    private boolean isRead = false;

    @Column(name = "read_at")
    private Instant readAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    public void prePersist() {
        if (this.id == null) {
            this.id = UUID.randomUUID();
        }
        if (this.createdAt == null) {
            this.createdAt = Instant.now();
        }
        if (this.category == null) {
            this.category = "GENERAL";
        }
    }

    public void markAsRead() {
        this.isRead = true;
        this.readAt = Instant.now();
    }
}
