package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;

import java.util.Date;

@Data
@Entity
@Table(name = "notification_support_ticket_notification_history")
public class SupportTicketNotificationHistoryEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "ticket_id", nullable = false)
    private Long ticketId;

    @Column(name = "notification_type", nullable = false, length = 50)
    private String notificationType;

    @Column(name = "channel", nullable = false, length = 20)
    private String channel; // EMAIL, PUSH, IN_APP

    @Column(name = "recipient_email")
    private String recipientEmail;

    @Column(name = "recipient_user_id", length = 100)
    private String recipientUserId;

    @Column(name = "status", nullable = false, length = 20)
    private String status = "SENT";

    @Column(name = "error_message", length = 500)
    private String errorMessage;

    @Column(name = "created_ts", nullable = false, updatable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdTs;

    @PrePersist
    protected void onCreate() {
        if (createdTs == null) {
            createdTs = new Date();
        }
        if (status == null) {
            status = "SENT";
        }
    }
}
