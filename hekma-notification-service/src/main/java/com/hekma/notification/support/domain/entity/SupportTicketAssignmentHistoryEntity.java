package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;

import java.util.Date;

@Data
@Entity
@Table(name = "notification_support_ticket_assignment_history")
public class SupportTicketAssignmentHistoryEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "ticket_id", nullable = false)
    private Long ticketId;

    @Column(name = "assigned_to_id", length = 100)
    private String assignedToId;

    @Column(name = "assigned_to_name")
    private String assignedToName;

    @Column(name = "assigned_team", length = 100)
    private String assignedTeam;

    @Column(name = "assigned_by_id", length = 100)
    private String assignedById;

    @Column(name = "assigned_by_name")
    private String assignedByName;

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
