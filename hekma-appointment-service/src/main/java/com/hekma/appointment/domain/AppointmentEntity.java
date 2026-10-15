package com.hekma.appointment.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;
import org.hibernate.annotations.SQLRestriction;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "appointment_appointments")
@SQLRestriction("is_deleted = false")
@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@AllArgsConstructor
public class AppointmentEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "tenant_path", nullable = false, length = 255)
    private String tenantPath;

    @Column(name = "from_key", nullable = false, length = 100)
    private String fromKey;

    @Column(name = "from_type", nullable = false, length = 50)
    private String fromType;

    @Column(name = "from_name")
    private String fromName;

    @Column(name = "from_email")
    private String fromEmail;

    @Column(name = "to_key", nullable = false, length = 100)
    private String toKey;

    @Column(name = "to_type", nullable = false, length = 50)
    private String toType;

    @Column(name = "to_name")
    private String toName;

    @Column(name = "to_email")
    private String toEmail;

    @Column(name = "start_date_time", nullable = false)
    private Instant startDateTime;

    @Column(name = "end_date_time", nullable = false)
    private Instant endDateTime;

    @Column(name = "note", columnDefinition = "TEXT")
    private String note;

    @Column(name = "mail_subject")
    private String mailSubject;

    @Column(name = "mail_text", columnDefinition = "TEXT")
    private String mailText;

    @Column(name = "doc_mail_text", columnDefinition = "TEXT")
    private String docMailText;

    @Column(name = "nav_link", columnDefinition = "TEXT")
    private String navLink;

    @Column(name = "doc_nav_link", columnDefinition = "TEXT")
    private String docNavLink;

    @Column(name = "reference")
    private String reference;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 50)
    @Builder.Default
    private AppointmentStatus status = AppointmentStatus.CREATED;

    @Column(name = "notification_status", length = 50)
    private String notificationStatus;

    @Column(name = "reminder_7d_sent", nullable = false)
    @Builder.Default
    private boolean reminder7dSent = false;

    @Column(name = "reminder_1d_sent", nullable = false)
    @Builder.Default
    private boolean reminder1dSent = false;

    @Column(name = "reminder_1h_sent", nullable = false)
    @Builder.Default
    private boolean reminder1hSent = false;
}
