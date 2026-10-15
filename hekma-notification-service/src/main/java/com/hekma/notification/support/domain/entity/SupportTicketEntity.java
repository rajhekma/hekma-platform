package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;
import org.hibernate.annotations.SQLRestriction;

import java.util.Date;
import java.util.UUID;

@Data
@Entity
@Table(name = "notification_support_ticket")
@SQLRestriction("is_deleted = false")
public class SupportTicketEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "uuid", unique = true, updatable = false, nullable = false, length = 36)
    private String uuid = UUID.randomUUID().toString();

    @Column(name = "ticket_number", unique = true, nullable = false, length = 30)
    private String ticketNumber;

    @Column(name = "subject", nullable = false, length = 500)
    private String subject;

    @Column(name = "description", columnDefinition = "TEXT", nullable = false)
    private String description;

    @Column(name = "category", nullable = false, length = 50)
    private String category = "GENERAL";

    @Column(name = "status", nullable = false, length = 50)
    private String status = "RECEIVED";

    @Column(name = "priority", nullable = false, length = 20)
    private String priority = "MEDIUM";

    @Column(name = "participant_email", nullable = false)
    private String participantEmail;

    @Column(name = "participant_user_id", length = 100)
    private String participantUserId;

    @Column(name = "participant_user_type", length = 50)
    private String participantUserType;

    @Column(name = "assigned_agent_id", length = 100)
    private String assignedAgentId;

    @Column(name = "assigned_agent_name")
    private String assignedAgentName;

    @Column(name = "assigned_team", length = 100)
    private String assignedTeam;

    @Column(name = "study_id", length = 100)
    private String studyId;

    @Column(name = "resolution", columnDefinition = "TEXT")
    private String resolution;

    @Column(name = "tags", length = 500)
    private String tags;

    @Column(name = "is_escalated", nullable = false)
    private Boolean isEscalated = false;

    @Column(name = "escalated_at")
    @Temporal(TemporalType.TIMESTAMP)
    private Date escalatedAt;

    @Column(name = "escalated_by", length = 100)
    private String escalatedBy;

    @Column(name = "sla_due_at")
    @Temporal(TemporalType.TIMESTAMP)
    private Date slaDueAt;

    @Column(name = "sla_breached", nullable = false)
    private Boolean slaBreached = false;

    @Column(name = "diagnostics_json", columnDefinition = "TEXT")
    private String diagnosticsJson;

    @Column(name = "privacy_accepted", nullable = false)
    private Boolean privacyAccepted = false;

    @Column(name = "is_deleted", nullable = false)
    private Boolean isDeleted = false;

    @Column(name = "created_by", updatable = false, length = 100)
    private String createdBy;

    @Column(name = "created_ts", nullable = false, updatable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdTs;

    @Column(name = "modified_by", length = 100)
    private String modifiedBy;

    @Column(name = "modified_ts", nullable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date modifiedTs;

    @PrePersist
    protected void onCreate() {
        if (uuid == null) {
            uuid = UUID.randomUUID().toString();
        }
        if (createdTs == null) {
            createdTs = new Date();
        }
        if (modifiedTs == null) {
            modifiedTs = new Date();
        }
        if (isDeleted == null) {
            isDeleted = false;
        }
        if (isEscalated == null) {
            isEscalated = false;
        }
        if (slaBreached == null) {
            slaBreached = false;
        }
        if (privacyAccepted == null) {
            privacyAccepted = false;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        modifiedTs = new Date();
    }
}
