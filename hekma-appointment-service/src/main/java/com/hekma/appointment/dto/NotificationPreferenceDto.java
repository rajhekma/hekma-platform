package com.hekma.appointment.dto;

import com.hekma.appointment.domain.NotificationPreferenceEntity;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
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
@Schema(description = "User notification channel toggles")
public class NotificationPreferenceDto {

    private UUID id;

    @NotBlank(message = "userId is required")
    private String userId;

    @NotBlank(message = "userType is required")
    private String userType;

    private Boolean toggleInApp;
    private Boolean toggleEmail;
    private Boolean toggleMessage;
    private Instant createdAt;
    private Instant modifiedTs;

    public static NotificationPreferenceDto fromEntity(NotificationPreferenceEntity entity) {
        return NotificationPreferenceDto.builder()
                .id(entity.getId())
                .userId(entity.getUserId())
                .userType(entity.getUserType())
                .toggleInApp(entity.isToggleInApp())
                .toggleEmail(entity.isToggleEmail())
                .toggleMessage(entity.isToggleMessage())
                .createdAt(entity.getCreatedAt())
                .modifiedTs(entity.getUpdatedAt())
                .build();
    }
}
