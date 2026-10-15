package com.hekma.appointment.controller;

import com.hekma.appointment.domain.AppointmentStatus;
import com.hekma.appointment.dto.AppointmentRequest;
import com.hekma.appointment.dto.AppointmentResponse;
import com.hekma.appointment.dto.ConflictCheckRequest;
import com.hekma.appointment.dto.ConflictCheckResponse;
import com.hekma.appointment.security.AppointmentPrincipal;
import com.hekma.appointment.service.AppointmentService;
import com.hekma.appointment.service.ConflictDetectionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/appointments")
@RequiredArgsConstructor
@Tag(name = "Appointments", description = "Endpoints for scheduling, managing, and searching appointments")
public class AppointmentController {

    private final AppointmentService appointmentService;
    private final ConflictDetectionService conflictDetectionService;

    @PostMapping
    @Operation(summary = "Schedule a new appointment", description = "Runs pre-flight conflict checks, persists the appointment, and triggers confirmations.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentResponse> createAppointment(
            @Valid @RequestBody AppointmentRequest request,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        AppointmentResponse response = appointmentService.createAppointment(request, principal);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get appointment by ID", description = "Retrieves an appointment by its UUID.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentResponse> getAppointment(
            @PathVariable UUID id,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(appointmentService.getAppointmentById(id, principal));
    }

    @GetMapping
    @Operation(summary = "Search appointments", description = "Filter appointments by participants, date ranges, and status.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Page<AppointmentResponse>> searchAppointments(
            @RequestParam(required = false) String fromKey,
            @RequestParam(required = false) String fromType,
            @RequestParam(required = false) String toKey,
            @RequestParam(required = false) String toType,
            @RequestParam(required = false) Instant startDateTime,
            @RequestParam(required = false) Instant endDateTime,
            @RequestParam(required = false) AppointmentStatus status,
            @PageableDefault(size = 20) Pageable pageable,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(appointmentService.searchAppointments(
                fromKey, fromType, toKey, toType, startDateTime, endDateTime, status, pageable, principal
        ));
    }

    @PutMapping("/{id}")
    @Operation(summary = "Update appointment details", description = "Reschedules appointment time, runs conflict checks, and sends update notices.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentResponse> updateAppointmentDetails(
            @PathVariable UUID id,
            @Valid @RequestBody AppointmentRequest request,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(appointmentService.updateAppointmentDetails(id, request, principal));
    }

    @PatchMapping("/{id}/status")
    @Operation(summary = "Update appointment status", description = "Change appointment status (e.g. CANCELLED or CLOSED).")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentResponse> updateStatus(
            @PathVariable UUID id,
            @RequestParam AppointmentStatus status,
            @RequestParam(required = false) String note,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(appointmentService.updateStatus(id, status, note, principal));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "Cancel / close an appointment", description = "Soft closes the appointment and sends cancellation notices.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentResponse> deleteAppointment(
            @PathVariable UUID id,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(appointmentService.updateStatus(id, AppointmentStatus.CANCELLED, "Cancelled by user", principal));
    }

    @PostMapping("/check-conflicts")
    @Operation(summary = "Check for schedule conflicts", description = "Tests whether a proposed appointment time overlaps with existing commitments.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<ConflictCheckResponse> checkConflicts(@Valid @RequestBody ConflictCheckRequest request) {
        return ResponseEntity.ok(conflictDetectionService.checkConflicts(request));
    }
}
