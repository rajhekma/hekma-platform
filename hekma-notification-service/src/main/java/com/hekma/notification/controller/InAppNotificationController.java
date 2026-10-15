package com.hekma.notification.controller;

import com.hekma.notification.dto.InAppNotificationDto;
import com.hekma.notification.dto.PagedResponse;
import com.hekma.notification.dto.UnreadCountDto;
import com.hekma.notification.service.InAppNotificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/in-app-notifications")
@RequiredArgsConstructor
@Tag(name = "In-App Notifications", description = "Endpoints for user in-app notification inbox")
public class InAppNotificationController {

    private final InAppNotificationService inAppService;

    @GetMapping
    @Operation(summary = "Get in-app notifications for a user", description = "Retrieves paginated notifications for the given user ID.")
    public ResponseEntity<PagedResponse<InAppNotificationDto>> getUserNotifications(
            @Parameter(description = "User ID", required = true) @RequestParam String userId,
            @Parameter(description = "Filter unread only") @RequestParam(required = false) Boolean unreadOnly,
            @PageableDefault(size = 20) Pageable pageable) {
        Page<InAppNotificationDto> page = inAppService.getUserNotifications(userId, unreadOnly, pageable);
        return ResponseEntity.ok(PagedResponse.from(page));
    }

    @GetMapping("/unread-count")
    @Operation(summary = "Get unread notifications count", description = "Returns total count of unread in-app notifications for the user.")
    public ResponseEntity<UnreadCountDto> getUnreadCount(
            @Parameter(description = "User ID", required = true) @RequestParam String userId) {
        UnreadCountDto count = inAppService.getUnreadCount(userId);
        return ResponseEntity.ok(count);
    }

    @PatchMapping("/{id}/read")
    @Operation(summary = "Mark a notification as read", description = "Marks a specific notification as read by its ID.")
    public ResponseEntity<InAppNotificationDto> markAsRead(@PathVariable UUID id) {
        InAppNotificationDto updated = inAppService.markAsRead(id);
        return ResponseEntity.ok(updated);
    }

    @PatchMapping("/read-all")
    @Operation(summary = "Mark all notifications as read", description = "Marks all unread notifications as read for a given user ID.")
    public ResponseEntity<Map<String, Object>> markAllAsRead(
            @Parameter(description = "User ID", required = true) @RequestParam String userId) {
        int count = inAppService.markAllAsRead(userId);
        return ResponseEntity.ok(Map.of(
                "userId", userId,
                "markedAsReadCount", count
        ));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "Delete an in-app notification", description = "Deletes a notification from user's inbox.")
    public ResponseEntity<Void> deleteNotification(@PathVariable UUID id) {
        inAppService.deleteNotification(id);
        return ResponseEntity.noContent().build();
    }
}
