package com.hekma.notification.dto;

import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationStatus;
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
@Schema(description = "Response details for a dispatched notification")
public class NotificationResponse {

    @Schema(description = "Unique ID of the notification tracking log")
    private UUID id;

    @Schema(description = "Channel through which notification was sent")
    private NotificationChannel channel;

    @Schema(description = "Recipient identifier")
    private String recipient;

    @Schema(description = "Current notification status")
    private NotificationStatus status;

    @Schema(description = "Provider response or reference ID")
    private String providerMessageId;

    @Schema(description = "Error message if delivery failed")
    private String errorMessage;

    @Schema(description = "Creation timestamp")
    private Instant createdAt;
}
