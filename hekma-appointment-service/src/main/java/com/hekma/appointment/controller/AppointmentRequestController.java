package com.hekma.appointment.controller;

import com.hekma.appointment.domain.RequestStatus;
import com.hekma.appointment.dto.AppointmentRequestDto;
import com.hekma.appointment.security.AppointmentPrincipal;
import com.hekma.appointment.service.AppointmentRequestService;
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

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/appointments/requests")
@RequiredArgsConstructor
@Tag(name = "Appointment Requests", description = "Endpoints for submitting and reviewing appointment/reactivation requests")
public class AppointmentRequestController {

    private final AppointmentRequestService requestService;

    @PostMapping
    @Operation(summary = "Submit an appointment request", description = "Create a request (e.g. from patient or clinic).")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentRequestDto> createRequest(
            @Valid @RequestBody AppointmentRequestDto dto,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        AppointmentRequestDto created = requestService.createRequest(dto, principal);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get request details", description = "Retrieve an appointment request by ID.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentRequestDto> getRequest(
            @PathVariable UUID id,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(requestService.getRequestById(id, principal));
    }

    @GetMapping
    @Operation(summary = "List appointment requests", description = "Fetch appointment requests filtered by status.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Page<AppointmentRequestDto>> listRequests(
            @RequestParam(required = false) RequestStatus status,
            @PageableDefault(size = 20) Pageable pageable,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(requestService.listRequests(status, pageable, principal));
    }

    @PatchMapping("/{id}/status")
    @Operation(summary = "Update request status", description = "Accept, reject, or close a request with an audit message.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AppointmentRequestDto> updateStatus(
            @PathVariable UUID id,
            @RequestParam RequestStatus status,
            @RequestParam(required = false) String response,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        return ResponseEntity.ok(requestService.updateRequestStatus(id, status, response, principal));
    }
}
