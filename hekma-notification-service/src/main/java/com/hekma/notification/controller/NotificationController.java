package com.hekma.notification.controller;

import com.hekma.notification.dto.BroadcastNotificationRequest;
import com.hekma.notification.dto.BroadcastNotificationResponse;
import com.hekma.notification.dto.NotificationResponse;
import com.hekma.notification.dto.NotificationSendRequest;
import com.hekma.notification.service.NotificationDispatcherService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/notifications")
@RequiredArgsConstructor
@Tag(name = "Notification Dispatcher", description = "Endpoints for other Hekma microservices to dispatch notifications")
public class NotificationController {

    private final NotificationDispatcherService dispatcherService;

    @PostMapping("/send")
    @Operation(
            summary = "Send a notification via a specific channel",
            description = "Dispatches a notification (Email, SMS, Push, or In-App). Supports async execution by default.",
            parameters = {
                    @Parameter(name = "X-Hekma-Service-Key", in = ParameterIn.HEADER, description = "Service API Key for inter-service authentication", required = true)
            }
    )
    public ResponseEntity<NotificationResponse> sendNotification(@Valid @RequestBody NotificationSendRequest request) {
        NotificationResponse response = dispatcherService.sendNotification(request);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(response);
    }

    @PostMapping("/broadcast")
    @Operation(
            summary = "Broadcast a notification to multiple channels simultaneously",
            description = "Dispatches an alert to multiple channels (e.g. Email, SMS, Push, In-App) for a user.",
            parameters = {
                    @Parameter(name = "X-Hekma-Service-Key", in = ParameterIn.HEADER, description = "Service API Key for inter-service authentication", required = true)
            }
    )
    public ResponseEntity<BroadcastNotificationResponse> broadcastNotification(@Valid @RequestBody BroadcastNotificationRequest request) {
        BroadcastNotificationResponse response = dispatcherService.broadcast(request);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{id}/status")
    @Operation(
            summary = "Get notification delivery status",
            description = "Retrieves the status (PENDING, SENT, DELIVERED, FAILED) of a previously dispatched notification.",
            parameters = {
                    @Parameter(name = "X-Hekma-Service-Key", in = ParameterIn.HEADER, description = "Service API Key for inter-service authentication", required = true)
            }
    )
    public ResponseEntity<NotificationResponse> getNotificationStatus(@PathVariable UUID id) {
        NotificationResponse response = dispatcherService.getStatus(id);
        return ResponseEntity.ok(response);
    }
}
