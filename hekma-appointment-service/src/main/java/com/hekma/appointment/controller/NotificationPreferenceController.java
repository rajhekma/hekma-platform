package com.hekma.appointment.controller;

import com.hekma.appointment.dto.NotificationPreferenceDto;
import com.hekma.appointment.security.AppointmentPrincipal;
import com.hekma.appointment.service.NotificationPreferenceService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/appointments/preferences")
@RequiredArgsConstructor
@Tag(name = "Notification Preferences", description = "Endpoints for managing notification channel preferences")
public class NotificationPreferenceController {

    private final NotificationPreferenceService preferenceService;

    @GetMapping
    @Operation(summary = "Get user notification preferences")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<NotificationPreferenceDto> getPreference(
            @RequestParam String userId,
            @RequestParam String userType) {
        return ResponseEntity.ok(preferenceService.getPreference(userId, userType));
    }

    @PutMapping
    @Operation(summary = "Update user notification preferences")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<NotificationPreferenceDto> updatePreference(
            @RequestParam String userId,
            @RequestParam String userType,
            @RequestParam(required = false) Boolean toggleInApp,
            @RequestParam(required = false) Boolean toggleEmail,
            @RequestParam(required = false) Boolean toggleMessage) {
        return ResponseEntity.ok(preferenceService.updatePreference(userId, userType, toggleInApp, toggleEmail, toggleMessage));
    }
}
