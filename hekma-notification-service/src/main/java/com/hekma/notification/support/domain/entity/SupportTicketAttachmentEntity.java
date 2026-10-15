package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;
import org.hibernate.annotations.SQLRestriction;

import java.util.Date;
import java.util.UUID;

@Data
@Entity
@Table(name = "notification_support_ticket_attachment")
@SQLRestriction("is_deleted = false")
public class SupportTicketAttachmentEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "uuid", unique = true, updatable = false, nullable = false, length = 36)
    private String uuid = UUID.randomUUID().toString();

    @Column(name = "ticket_id", nullable = false)
    private Long ticketId;

    @Column(name = "comment_id")
    private Long commentId;

    @Column(name = "file_name", nullable = false, length = 500)
    private String fileName;

    @Column(name = "file_url", nullable = false, length = 1000)
    private String fileUrl;

    @Column(name = "file_size")
    private Long fileSize;

    @Column(name = "mime_type", length = 100)
    private String mimeType;

    @Column(name = "scan_status", nullable = false, length = 30)
    private String scanStatus = "CLEAN";

    @Column(name = "uploaded_by", length = 100)
    private String uploadedBy;

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
        if (isDeleted == null) {
            isDeleted = false;
        }
        if (scanStatus == null) {
            scanStatus = "CLEAN";
        }
    }
}
