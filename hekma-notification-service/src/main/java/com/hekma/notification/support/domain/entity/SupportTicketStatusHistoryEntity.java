package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;

import java.util.Date;

@Data
@Entity
@Table(name = "notification_support_ticket_status_history")
public class SupportTicketStatusHistoryEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "ticket_id", nullable = false)
    private Long ticketId;

    @Column(name = "from_status", length = 50)
    private String fromStatus;

    @Column(name = "to_status", nullable = false, length = 50)
    private String toStatus;

    @Column(name = "changed_by_id", length = 100)
    private String changedById;

    @Column(name = "changed_by_name")
    private String changedByName;

    @Column(name = "notes", length = 500)
    private String notes;

    @Column(name = "created_ts", nullable = false, updatable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdTs;

    @PrePersist
    protected void onCreate() {
        if (createdTs == null) {
            createdTs = new Date();
        }
    }
}
