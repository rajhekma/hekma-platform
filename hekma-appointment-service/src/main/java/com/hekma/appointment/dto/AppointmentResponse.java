package com.hekma.appointment.dto;

import com.hekma.appointment.domain.AppointmentEntity;
import com.hekma.appointment.domain.AppointmentStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Representation of a scheduled appointment")
public class AppointmentResponse {

    @Schema(description = "Unique appointment UUID")
    private UUID id;

    @Schema(description = "String alias for legacy GraphQL compatibility")
    private String appointmentId;

    private UUID tenantId;
    private String tenantPath;
    private String fromKey;
    private String fromType;
    private String fromName;
    private String fromEmail;
    private String toKey;
    private String toType;
    private String toName;
    private String toEmail;
    private Instant startDateTime;
    private Instant endDateTime;
    private String note;
    private String mailSubject;
    private String mailText;
    private String docMailText;
    private String navLink;
    private String docNavLink;
    private String reference;
    private AppointmentStatus status;
    private String notificationStatus;
    private boolean reminder7dSent;
    private boolean reminder1dSent;
    private boolean reminder1hSent;
    private Instant createdAt;
    private Instant updatedAt;

    public static AppointmentResponse fromEntity(AppointmentEntity entity) {
        return AppointmentResponse.builder()
                .id(entity.getId())
                .appointmentId(entity.getId() != null ? entity.getId().toString() : null)
                .tenantId(entity.getTenantId())
                .tenantPath(entity.getTenantPath())
                .fromKey(entity.getFromKey())
                .fromType(entity.getFromType())
                .fromName(entity.getFromName())
                .fromEmail(entity.getFromEmail())
                .toKey(entity.getToKey())
                .toType(entity.getToType())
                .toName(entity.getToName())
                .toEmail(entity.getToEmail())
                .startDateTime(entity.getStartDateTime())
                .endDateTime(entity.getEndDateTime())
                .note(entity.getNote())
                .mailSubject(entity.getMailSubject())
                .mailText(entity.getMailText())
                .docMailText(entity.getDocMailText())
                .navLink(entity.getNavLink())
                .docNavLink(entity.getDocNavLink())
                .reference(entity.getReference())
                .status(entity.getStatus())
                .notificationStatus(entity.getNotificationStatus())
                .reminder7dSent(entity.isReminder7dSent())
                .reminder1dSent(entity.isReminder1dSent())
                .reminder1hSent(entity.isReminder1hSent())
                .createdAt(entity.getCreatedAt())
                .updatedAt(entity.getUpdatedAt())
                .build();
    }

    public String getFromMail() {
        return fromEmail;
    }

    public String getToMail() {
        return toEmail;
    }
}
