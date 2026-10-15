package com.hekma.notification.dto;

import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationPriority;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload for broadcasting a notification across multiple channels simultaneously")
public class BroadcastNotificationRequest {

    @NotEmpty(message = "At least one channel must be specified")
    @Schema(description = "Channels to broadcast to", example = "[\"EMAIL\", \"IN_APP\", \"PUSH\"]")
    private List<NotificationChannel> channels;

    @Schema(description = "User ID (required if IN_APP channel is selected)", example = "usr_998877")
    private String userId;

    @Schema(description = "Email address (required if EMAIL channel is selected)", example = "doctor@hekma.com")
    private String email;

    @Schema(description = "Phone number in E.164 format (required if SMS channel is selected)", example = "+966501234567")
    private String phone;

    @Schema(description = "Device push token (required if PUSH channel is selected)", example = "fcm_token_xyz")
    private String pushToken;

    @Schema(description = "Notification title or subject", example = "Critical System Alert")
    private String title;

    @NotBlank(message = "Content body is required")
    @Schema(description = "Notification body content", example = "Your appointment has been confirmed.")
    private String content;

    @Builder.Default
    @Schema(description = "Priority level", example = "HIGH")
    private NotificationPriority priority = NotificationPriority.NORMAL;

    @Schema(description = "Custom metadata passed along with the notification")
    private Map<String, Object> metadata;

    @Schema(description = "Name of the calling Hekma service", example = "hekma_api")
    private String sourceService;
}
