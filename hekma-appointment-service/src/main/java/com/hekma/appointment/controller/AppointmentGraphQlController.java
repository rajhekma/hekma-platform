package com.hekma.appointment.controller;

import com.hekma.appointment.domain.AppointmentStatus;
import com.hekma.appointment.dto.ApiResponse;
import com.hekma.appointment.dto.AppointmentRequest;
import com.hekma.appointment.dto.AppointmentResponse;
import com.hekma.appointment.dto.NotificationPreferenceDto;
import com.hekma.appointment.dto.ReminderDto;
import com.hekma.appointment.security.AppointmentPrincipal;
import com.hekma.appointment.service.AppointmentService;
import com.hekma.appointment.service.NotificationPreferenceService;
import com.hekma.appointment.service.WebNotificationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Controller
@RequiredArgsConstructor
@Slf4j
public class AppointmentGraphQlController {

    private final AppointmentService appointmentService;
    private final NotificationPreferenceService preferenceService;
    private final WebNotificationService webNotificationService;

    @QueryMapping
    @PreAuthorize("isAuthenticated()")
    public List<AppointmentResponse> searchAppointment(
            @Argument String fromKey,
            @Argument String fromType,
            @Argument String toKey,
            @Argument String toType,
            @Argument String startDateTime,
            @Argument String endDateTime,
            @Argument String status,
            @AuthenticationPrincipal AppointmentPrincipal principal) {

        Instant start = parseInstant(startDateTime);
        Instant end = parseInstant(endDateTime);
        AppointmentStatus apptStatus = parseStatus(status);

        return appointmentService.searchAppointmentsList(
                fromKey, fromType, toKey, toType, start, end, apptStatus, principal
        );
    }

    @QueryMapping
    @PreAuthorize("isAuthenticated()")
    public List<ReminderDto> getReminders(
            @Argument String id,
            @Argument String type) {
        return webNotificationService.getReminders(id, type);
    }

    @QueryMapping
    @PreAuthorize("isAuthenticated()")
    public NotificationPreferenceDto getNotificationPreference(
            @Argument String userId,
            @Argument String userType) {
        return preferenceService.getPreference(userId, userType);
    }

    @MutationMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse createAppointment(
            @Argument String fromKey,
            @Argument String fromType,
            @Argument String fromName,
            @Argument String fromMail,
            @Argument String toKey,
            @Argument String toType,
            @Argument String toName,
            @Argument String toMail,
            @Argument String startDateTime,
            @Argument String endDateTime,
            @Argument String note,
            @Argument String mailSubject,
            @Argument String mailText,
            @Argument String docMailText,
            @Argument String navLink,
            @Argument String docNavLink,
            @Argument String reference,
            @AuthenticationPrincipal AppointmentPrincipal principal) {

        try {
            AppointmentRequest request = AppointmentRequest.builder()
                    .fromKey(fromKey)
                    .fromType(fromType)
                    .fromName(fromName)
                    .fromEmail(fromMail)
                    .toKey(toKey)
                    .toType(toType)
                    .toName(toName)
                    .toEmail(toMail)
                    .startDateTime(parseInstant(startDateTime))
                    .endDateTime(parseInstant(endDateTime))
                    .note(note)
                    .mailSubject(mailSubject)
                    .mailText(mailText)
                    .docMailText(docMailText)
                    .navLink(navLink)
                    .docNavLink(docNavLink)
                    .reference(reference)
                    .build();

            AppointmentResponse created = appointmentService.createAppointment(request, principal);
            return ApiResponse.success("Appointment created successfully.", created.getId().toString());
        } catch (Exception e) {
            log.error("GraphQL createAppointment failed: {}", e.getMessage());
            return ApiResponse.failed(400, e.getMessage());
        }
    }

    @MutationMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse updateAppointment(
            @Argument String appointmentId,
            @Argument String note,
            @Argument String status,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        try {
            UUID id = UUID.fromString(appointmentId);
            AppointmentStatus apptStatus = parseStatus(status);
            appointmentService.updateStatus(id, apptStatus != null ? apptStatus : AppointmentStatus.UPDATED, note, principal);
            return ApiResponse.success("Appointment updated successfully.", appointmentId);
        } catch (Exception e) {
            log.error("GraphQL updateAppointment failed: {}", e.getMessage());
            return ApiResponse.failed(400, e.getMessage());
        }
    }

    @MutationMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse updateAppointmentDetails(
            @Argument String appointmentId,
            @Argument String fromKey,
            @Argument String fromType,
            @Argument String fromName,
            @Argument String fromMail,
            @Argument String toKey,
            @Argument String toType,
            @Argument String toName,
            @Argument String toMail,
            @Argument String startDateTime,
            @Argument String endDateTime,
            @Argument String note,
            @Argument String mailSubject,
            @Argument String mailText,
            @Argument String docMailText,
            @Argument String navLink,
            @Argument String docNavLink,
            @Argument String reference,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        try {
            UUID id = UUID.fromString(appointmentId);
            AppointmentRequest request = AppointmentRequest.builder()
                    .fromKey(fromKey)
                    .fromType(fromType)
                    .fromName(fromName)
                    .fromEmail(fromMail)
                    .toKey(toKey)
                    .toType(toType)
                    .toName(toName)
                    .toEmail(toMail)
                    .startDateTime(parseInstant(startDateTime))
                    .endDateTime(parseInstant(endDateTime))
                    .note(note)
                    .mailSubject(mailSubject)
                    .mailText(mailText)
                    .docMailText(docMailText)
                    .navLink(navLink)
                    .docNavLink(docNavLink)
                    .reference(reference)
                    .build();

            AppointmentResponse updated = appointmentService.updateAppointmentDetails(id, request, principal);
            return ApiResponse.success("Appointment details updated successfully.", updated.getId().toString());
        } catch (Exception e) {
            log.error("GraphQL updateAppointmentDetails failed: {}", e.getMessage());
            return ApiResponse.failed(400, e.getMessage());
        }
    }

    @MutationMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse deleteAppointment(
            @Argument String appointmentId,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        try {
            UUID id = UUID.fromString(appointmentId);
            appointmentService.updateStatus(id, AppointmentStatus.CANCELLED, "Cancelled via GraphQL", principal);
            return ApiResponse.success("Appointment deleted successfully.", appointmentId);
        } catch (Exception e) {
            log.error("GraphQL deleteAppointment failed: {}", e.getMessage());
            return ApiResponse.failed(400, e.getMessage());
        }
    }

    @MutationMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse updateNotificationStatus(
            @Argument String appointmentId,
            @Argument String note,
            @Argument String status,
            @AuthenticationPrincipal AppointmentPrincipal principal) {
        try {
            UUID id = UUID.fromString(appointmentId);
            appointmentService.updateStatus(id, AppointmentStatus.UPDATED, note, principal);
            return ApiResponse.success("Notification status updated.", appointmentId);
        } catch (Exception e) {
            return ApiResponse.failed(400, e.getMessage());
        }
    }

    private Instant parseInstant(String dateStr) {
        if (dateStr == null || dateStr.isBlank()) {
            return null;
        }
        try {
            return Instant.parse(dateStr);
        } catch (Exception e) {
            // Support legacy timestamp format e.g. "yyyy-MM-dd HH:mm:ss"
            try {
                String normalized = dateStr.trim().replace(" ", "T");
                if (!normalized.endsWith("Z") && !normalized.contains("+") && normalized.indexOf("-", 10) == -1) {
                    normalized += "Z";
                }
                return Instant.parse(normalized);
            } catch (Exception ex) {
                log.warn("Failed to parse instant string '{}'", dateStr);
                return null;
            }
        }
    }

    private AppointmentStatus parseStatus(String status) {
        if (status == null || status.isBlank()) {
            return null;
        }
        try {
            return AppointmentStatus.valueOf(status.trim().toUpperCase());
        } catch (Exception e) {
            return null;
        }
    }
}
