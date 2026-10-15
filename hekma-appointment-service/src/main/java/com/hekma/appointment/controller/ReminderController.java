package com.hekma.appointment.controller;

import com.hekma.appointment.dto.ReminderDto;
import com.hekma.appointment.service.WebNotificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/appointments/reminders")
@RequiredArgsConstructor
@Tag(name = "In-App Reminders", description = "Endpoints for fetching and managing user in-app appointment reminders")
public class ReminderController {

    private final WebNotificationService webNotificationService;

    @GetMapping
    @Operation(summary = "Get user reminders and notifications")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<List<ReminderDto>> getReminders(
            @RequestParam String userId,
            @RequestParam String userType) {
        return ResponseEntity.ok(webNotificationService.getReminders(userId, userType));
    }

    @PatchMapping("/{id}/viewed")
    @Operation(summary = "Mark reminder as read")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Void> markViewed(@PathVariable UUID id) {
        webNotificationService.markViewed(id);
        return ResponseEntity.noContent().build();
    }
}
