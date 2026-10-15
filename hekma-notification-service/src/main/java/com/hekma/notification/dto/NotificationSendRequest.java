package com.hekma.notification.dto;

import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationPriority;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload for sending a notification via a specific channel")
public class NotificationSendRequest {

    @NotNull(message = "Channel is required (EMAIL, SMS, PUSH, IN_APP)")
    @Schema(description = "Target delivery channel", example = "EMAIL")
    private NotificationChannel channel;

    @NotBlank(message = "Recipient is required (email, phone number, device token, or user ID)")
    @Schema(description = "Recipient identifier (e.g. email address, E.164 phone, FCM token, or user ID)", example = "user@hekma.com")
    private String recipient;

    @Schema(description = "Notification title or subject", example = "Welcome to Hekma")
    private String title;

    @NotBlank(message = "Content body is required")
    @Schema(description = "Body content of the notification", example = "Your verification code is 123456")
    private String content;

    @Builder.Default
    @Schema(description = "Priority level", example = "NORMAL")
    private NotificationPriority priority = NotificationPriority.NORMAL;

    @Schema(description = "Optional template code", example = "VERIFICATION_OTP")
    private String templateCode;

    @Schema(description = "Template replacement parameters")
    private Map<String, Object> templateParams;

    @Schema(description = "Custom metadata passed along with the notification")
    private Map<String, Object> metadata;

    @Schema(description = "Name of the calling Hekma service", example = "hekma-identity-service")
    private String sourceService;

    @Schema(description = "Unique idempotency key to prevent duplicate sends", example = "req-12345-abcde")
    private String idempotencyKey;

    @Builder.Default
    @Schema(description = "Whether to process asynchronously", example = "true")
    private Boolean async = true;
}
