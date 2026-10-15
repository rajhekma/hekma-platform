package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;
import org.hibernate.annotations.SQLRestriction;

import java.util.Date;
import java.util.UUID;

@Data
@Entity
@Table(name = "notification_support_ticket_comment")
@SQLRestriction("is_deleted = false")
public class SupportTicketCommentEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "uuid", unique = true, updatable = false, nullable = false, length = 36)
    private String uuid = UUID.randomUUID().toString();

    @Column(name = "ticket_id", nullable = false)
    private Long ticketId;

    @Column(name = "author_id", length = 100)
    private String authorId;

    @Column(name = "author_name")
    private String authorName;

    @Column(name = "author_type", nullable = false, length = 50)
    private String authorType; // PARTICIPANT, AGENT, SYSTEM

    @Column(name = "comment_text", columnDefinition = "TEXT", nullable = false)
    private String commentText;

    @Column(name = "is_internal", nullable = false)
    private Boolean isInternal = false;

    @Column(name = "is_deleted", nullable = false)
    private Boolean isDeleted = false;

    @Column(name = "created_ts", nullable = false, updatable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdTs;

    @PrePersist
    protected void onCreate() {
        if (uuid == null) {
            uuid = UUID.randomUUID().toString();
        }
        if (createdTs == null) {
            createdTs = new Date();
        }
        if (isInternal == null) {
            isInternal = false;
        }
        if (isDeleted == null) {
            isDeleted = false;
        }
    }
}
