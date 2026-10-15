package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;

import java.util.Date;

@Data
@Entity
@Table(name = "notification_support_sla_tracking")
public class SupportSlaTrackingEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "ticket_id", unique = true, nullable = false)
    private Long ticketId;

    @Column(name = "sla_hours", nullable = false)
    private Integer slaHours = 48;

    @Column(name = "first_response_at")
    @Temporal(TemporalType.TIMESTAMP)
    private Date firstResponseAt;

    @Column(name = "resolved_at")
    @Temporal(TemporalType.TIMESTAMP)
    private Date resolvedAt;

    @Column(name = "due_at", nullable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date dueAt;

    @Column(name = "breached", nullable = false)
    private Boolean breached = false;

    @Column(name = "created_ts", nullable = false, updatable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdTs;

    @Column(name = "modified_ts", nullable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date modifiedTs;

    @PrePersist
    protected void onCreate() {
        if (createdTs == null) {
            createdTs = new Date();
        }
        if (modifiedTs == null) {
            modifiedTs = new Date();
        }
        if (breached == null) {
            breached = false;
        }
        if (slaHours == null) {
            slaHours = 48;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        modifiedTs = new Date();
    }
}
