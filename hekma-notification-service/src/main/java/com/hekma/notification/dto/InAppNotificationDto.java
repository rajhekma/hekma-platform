package com.hekma.notification.dto;

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
@Schema(description = "In-App notification representation for user inbox")
public class InAppNotificationDto {

    @Schema(description = "Notification ID")
    private UUID id;

    @Schema(description = "User ID")
    private String userId;

    @Schema(description = "Notification title")
    private String title;

    @Schema(description = "Notification message content")
    private String content;

    @Schema(description = "Category (e.g. GENERAL, ALERT, REMINDER)")
    private String category;

    @Schema(description = "Deep link or action URL")
    private String actionUrl;

    @Schema(description = "Custom data payload as JSON string")
    private String dataJson;

    @Schema(description = "Whether notification has been read")
    private boolean isRead;

    @Schema(description = "Timestamp when notification was read")
    private Instant readAt;

    @Schema(description = "Creation timestamp")
    private Instant createdAt;
}
