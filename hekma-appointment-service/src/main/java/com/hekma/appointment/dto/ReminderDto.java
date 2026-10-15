package com.hekma.appointment.dto;

import com.hekma.appointment.domain.ViewedStatus;
import com.hekma.appointment.domain.WebNotificationEntity;
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
@Schema(description = "In-app web notification / reminder record")
public class ReminderDto {

    private UUID id;
    private String userId;
    private String userType;
    private String referenceId;
    private String referenceType;
    private Instant referenceTimestamp;
    private String startDateTime;
    private String notificationType;
    private String message;
    private ViewedStatus viewedStatus;
    private Instant createdAt;

    public static ReminderDto fromEntity(WebNotificationEntity entity) {
        return ReminderDto.builder()
                .id(entity.getId())
                .userId(entity.getUserId())
                .userType(entity.getUserType())
                .referenceId(entity.getReferenceId())
                .referenceType(entity.getReferenceType())
                .referenceTimestamp(entity.getReferenceTimestamp())
                .startDateTime(entity.getReferenceTimestamp() != null ? entity.getReferenceTimestamp().toString() : null)
                .notificationType(entity.getNotificationType())
                .message(entity.getMessage())
                .viewedStatus(entity.getViewedStatus())
                .createdAt(entity.getCreatedAt())
                .build();
    }

    public String getCreatedTs() {
        return createdAt != null ? createdAt.toString() : null;
    }
}
