package com.hekma.appointment.service;

import com.hekma.appointment.domain.AppointmentEntity;
import com.hekma.appointment.domain.AppointmentStatus;
import com.hekma.appointment.dto.AppointmentRequest;
import com.hekma.appointment.dto.AppointmentResponse;
import com.hekma.appointment.exception.ResourceNotFoundException;
import com.hekma.appointment.exception.UnauthorizedOperationException;
import com.hekma.appointment.notification.NotificationServiceClient;
import com.hekma.appointment.repository.AppointmentRepository;
import com.hekma.appointment.security.AppointmentPrincipal;
import jakarta.persistence.criteria.Predicate;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class AppointmentService {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a")
            .withZone(ZoneOffset.UTC);

    private final AppointmentRepository appointmentRepository;
    private final ConflictDetectionService conflictDetectionService;
    private final NotificationServiceClient notificationServiceClient;
    private final NotificationPreferenceService notificationPreferenceService;
    private final WebNotificationService webNotificationService;

    @Transactional
    public AppointmentResponse createAppointment(AppointmentRequest request, AppointmentPrincipal principal) {
        log.info("Scheduling appointment between {} ({}) and {} ({})",
                request.getFromKey(), request.getFromType(), request.getToKey(), request.getToType());

        // 1. Conflict detection
        conflictDetectionService.assertNoConflict(
                request.getFromKey(), request.getFromType(), request.getFromName(),
                request.getToKey(), request.getToType(), request.getToName(),
                request.getStartDateTime(), request.getEndDateTime(),
                null
        );

        // 2. Resolve tenant context
        UUID tenantId = (principal != null && principal.tenantId() != null)
                ? principal.tenantId()
                : UUID.fromString("00000000-0000-0000-0000-000000000001");
        String tenantPath = (principal != null && principal.tenantPath() != null)
                ? principal.tenantPath()
                : "/" + tenantId + "/";

        // 3. Build & persist entity
        AppointmentEntity entity = AppointmentEntity.builder()
                .tenantId(tenantId)
                .tenantPath(tenantPath)
                .fromKey(request.getFromKey())
                .fromType(request.getFromType())
                .fromName(request.getFromName())
                .fromEmail(request.getFromEmail())
                .toKey(request.getToKey())
                .toType(request.getToType())
                .toName(request.getToName())
                .toEmail(request.getToEmail())
                .startDateTime(request.getStartDateTime())
                .endDateTime(request.getEndDateTime())
                .note(request.getNote())
                .mailSubject(request.getMailSubject())
                .mailText(request.getMailText())
                .docMailText(request.getDocMailText())
                .navLink(request.getNavLink())
                .docNavLink(request.getDocNavLink())
                .reference(request.getReference())
                .status(AppointmentStatus.CREATED)
                .reminder1hSent(false)
                .reminder1dSent(false)
                .reminder7dSent(false)
                .build();

        AppointmentEntity saved = appointmentRepository.save(entity);
        log.info("Created appointment with ID: {}", saved.getId());

        // 4. Web notification
        String formattedDate = DATE_TIME_FORMATTER.format(saved.getStartDateTime());
        webNotificationService.createReminder(
                saved.getToKey(), saved.getToType(),
                saved.getId().toString(), "Appointments",
                saved.getStartDateTime(), "Appointments",
                "Your appointment with " + saved.getFromName() + " is confirmed for " + formattedDate
        );

        // 5. Outbound notifications
        dispatchNotifications(saved, "Created");

        return AppointmentResponse.fromEntity(saved);
    }

    @Transactional
    public AppointmentResponse updateAppointmentDetails(UUID appointmentId, AppointmentRequest request, AppointmentPrincipal principal) {
        AppointmentEntity entity = getAppointmentEntity(appointmentId);
        validateTenantAccess(entity, principal);

        log.info("Updating appointment details for ID: {}", appointmentId);

        // 1. Conflict detection (excluding current appointment)
        conflictDetectionService.assertNoConflict(
                request.getFromKey(), request.getFromType(), request.getFromName(),
                request.getToKey(), request.getToType(), request.getToName(),
                request.getStartDateTime(), request.getEndDateTime(),
                appointmentId
        );

        // 2. Update fields
        entity.setFromKey(request.getFromKey());
        entity.setFromType(request.getFromType());
        entity.setFromName(request.getFromName());
        entity.setFromEmail(request.getFromEmail());
        entity.setToKey(request.getToKey());
        entity.setToType(request.getToType());
        entity.setToName(request.getToName());
        entity.setToEmail(request.getToEmail());
        entity.setStartDateTime(request.getStartDateTime());
        entity.setEndDateTime(request.getEndDateTime());
        entity.setNote(request.getNote());
        entity.setMailSubject(request.getMailSubject());
        entity.setMailText(request.getMailText());
        entity.setDocMailText(request.getDocMailText());
        entity.setNavLink(request.getNavLink());
        entity.setDocNavLink(request.getDocNavLink());
        entity.setReference(request.getReference());
        entity.setStatus(AppointmentStatus.UPDATED);

        // Reset reminders for updated time
        entity.setReminder1hSent(false);
        entity.setReminder1dSent(false);
        entity.setReminder7dSent(false);
        entity.setNotificationStatus(null);

        AppointmentEntity saved = appointmentRepository.save(entity);

        // 3. Clean previous reminders and create new in-app notification
        webNotificationService.deleteRemindersForReference(appointmentId.toString(), "Appointments");
        String formattedDate = DATE_TIME_FORMATTER.format(saved.getStartDateTime());
        webNotificationService.createReminder(
                saved.getToKey(), saved.getToType(),
                saved.getId().toString(), "Appointments",
                saved.getStartDateTime(), "Appointments",
                "Your appointment with " + saved.getFromName() + " has been updated to " + formattedDate
        );

        // 4. Outbound notifications
        dispatchNotifications(saved, "Updated");

        return AppointmentResponse.fromEntity(saved);
    }

    @Transactional
    public AppointmentResponse updateStatus(UUID appointmentId, AppointmentStatus status, String note, AppointmentPrincipal principal) {
        AppointmentEntity entity = getAppointmentEntity(appointmentId);
        validateTenantAccess(entity, principal);

        log.info("Updating appointment {} status to {}", appointmentId, status);
        entity.setStatus(status);
        if (note != null && !note.isBlank()) {
            entity.setNote(note);
        }

        AppointmentEntity saved = appointmentRepository.save(entity);

        if (status == AppointmentStatus.CLOSED || status == AppointmentStatus.CANCELLED) {
            webNotificationService.deleteRemindersForReference(appointmentId.toString(), "Appointments");
            dispatchNotifications(saved, "Closed");
        }

        return AppointmentResponse.fromEntity(saved);
    }

    @Transactional(readOnly = true)
    public AppointmentResponse getAppointmentById(UUID appointmentId, AppointmentPrincipal principal) {
        AppointmentEntity entity = getAppointmentEntity(appointmentId);
        validateTenantAccess(entity, principal);
        return AppointmentResponse.fromEntity(entity);
    }

    @Transactional(readOnly = true)
    public Page<AppointmentResponse> searchAppointments(
            String fromKey, String fromType, String toKey, String toType,
            Instant startDateTime, Instant endDateTime, AppointmentStatus status,
            Pageable pageable, AppointmentPrincipal principal) {

        Specification<AppointmentEntity> spec = buildSearchSpecification(
                fromKey, fromType, toKey, toType, startDateTime, endDateTime, status, principal
        );

        return appointmentRepository.findAll(spec, pageable).map(AppointmentResponse::fromEntity);
    }

    @Transactional(readOnly = true)
    public List<AppointmentResponse> searchAppointmentsList(
            String fromKey, String fromType, String toKey, String toType,
            Instant startDateTime, Instant endDateTime, AppointmentStatus status,
            AppointmentPrincipal principal) {

        Specification<AppointmentEntity> spec = buildSearchSpecification(
                fromKey, fromType, toKey, toType, startDateTime, endDateTime, status, principal
        );

        return appointmentRepository.findAll(spec).stream()
                .map(AppointmentResponse::fromEntity)
                .toList();
    }

    private Specification<AppointmentEntity> buildSearchSpecification(
            String fromKey, String fromType, String toKey, String toType,
            Instant startDateTime, Instant endDateTime, AppointmentStatus status,
            AppointmentPrincipal principal) {

        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (fromKey != null && !fromKey.isBlank()) {
                predicates.add(cb.equal(root.get("fromKey"), fromKey.trim()));
            }
            if (fromType != null && !fromType.isBlank()) {
                predicates.add(cb.equal(cb.lower(root.get("fromType")), fromType.trim().toLowerCase()));
            }
            if (toKey != null && !toKey.isBlank()) {
                predicates.add(cb.equal(root.get("toKey"), toKey.trim()));
            }
            if (toType != null && !toType.isBlank()) {
                predicates.add(cb.equal(cb.lower(root.get("toType")), toType.trim().toLowerCase()));
            }
            if (startDateTime != null) {
                predicates.add(cb.greaterThanOrEqualTo(root.get("startDateTime"), startDateTime));
            }
            if (endDateTime != null) {
                predicates.add(cb.lessThanOrEqualTo(root.get("endDateTime"), endDateTime));
            }
            if (status != null) {
                predicates.add(cb.equal(root.get("status"), status));
            }

            // Tenant subtree scoping
            if (principal != null && !principal.isPlatformAdmin() && principal.tenantPath() != null) {
                predicates.add(cb.like(root.get("tenantPath"), principal.tenantPath() + "%"));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }

    private AppointmentEntity getAppointmentEntity(UUID appointmentId) {
        return appointmentRepository.findById(appointmentId)
                .orElseThrow(() -> new ResourceNotFoundException("Appointment not found with ID: " + appointmentId));
    }

    private void validateTenantAccess(AppointmentEntity entity, AppointmentPrincipal principal) {
        if (principal == null || principal.isPlatformAdmin()) {
            return;
        }
        if (!principal.isWithinSubtree(entity.getTenantPath())) {
            throw new UnauthorizedOperationException("Cannot access appointment outside of your tenant subtree.");
        }
    }

    private void dispatchNotifications(AppointmentEntity appt, String actionType) {
        String formattedDate = DATE_TIME_FORMATTER.format(appt.getStartDateTime());
        String doctorName = appt.getFromName() != null ? appt.getFromName() : "Doctor";
        String patientName = appt.getToName() != null ? appt.getToName() : "Patient";
        String description = appt.getNote() != null ? appt.getNote() : "-";

        String subject;
        String emailBody;
        String pushTitle;
        String pushBody;

        if ("Created".equalsIgnoreCase(actionType)) {
            subject = "Your Appointment is Confirmed â€“ Dr. " + doctorName + ", " + formattedDate;
            emailBody = String.format("<p>Hi %s,</p><p>Your appointment has been confirmed with Dr. %s on %s.</p><p>Note: %s</p>",
                    patientName, doctorName, formattedDate, description);
            pushTitle = "Appointment Confirmed";
            pushBody = "Your appointment with Dr. " + doctorName + " is confirmed for " + formattedDate;
        } else if ("Updated".equalsIgnoreCase(actionType)) {
            subject = "Your Appointment Has Been Updated â€“ Dr. " + doctorName + ", " + formattedDate;
            emailBody = String.format("<p>Hi %s,</p><p>Your appointment with Dr. %s has been rescheduled to %s.</p><p>Note: %s</p>",
                    patientName, doctorName, formattedDate, description);
            pushTitle = "Appointment Updated";
            pushBody = "Your appointment with Dr. " + doctorName + " has been rescheduled to " + formattedDate;
        } else {
            subject = "Your Appointment Has Been Cancelled â€“ Dr. " + doctorName + ", " + formattedDate;
            emailBody = String.format("<p>Hi %s,</p><p>Your appointment with Dr. %s on %s has been cancelled.</p>",
                    patientName, doctorName, formattedDate);
            pushTitle = "Appointment Cancelled";
            pushBody = "Your appointment with Dr. " + doctorName + " has been cancelled.";
        }

        // Email dispatch if preference enabled
        if (appt.getToEmail() != null && notificationPreferenceService.isNotificationEnabled(appt.getToKey(), appt.getToType(), "EMAIL")) {
            notificationServiceClient.sendAppointmentEmail(appt.getToEmail(), subject, emailBody, appt.getId().toString(), actionType);
        }

        // Push notification dispatch if preference enabled
        if (notificationPreferenceService.isNotificationEnabled(appt.getToKey(), appt.getToType(), "PUSH")) {
            notificationServiceClient.sendAppointmentPush(appt.getToKey(), pushTitle, pushBody, appt.getId().toString(), actionType);
        }
    }
}
