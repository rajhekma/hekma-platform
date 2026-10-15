package com.hekma.appointment.scheduler;

import com.hekma.appointment.domain.AppointmentEntity;
import com.hekma.appointment.domain.AppointmentStatus;
import com.hekma.appointment.notification.NotificationServiceClient;
import com.hekma.appointment.repository.AppointmentRepository;
import com.hekma.appointment.service.NotificationPreferenceService;
import com.hekma.appointment.service.WebNotificationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.List;

@Component
@EnableScheduling
@RequiredArgsConstructor
@Slf4j
public class AppointmentReminderScheduler {

    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a")
            .withZone(ZoneOffset.UTC);

    private final AppointmentRepository appointmentRepository;
    private final NotificationServiceClient notificationServiceClient;
    private final NotificationPreferenceService notificationPreferenceService;
    private final WebNotificationService webNotificationService;

    @Scheduled(cron = "0 * * * * *", zone = "UTC")
    @Transactional
    public void processReminders() {
        Instant now = Instant.now();

        // 1. Process 1-Hour Reminders (appointments starting in [50, 70] minutes)
        Instant start1h = now.plus(50, ChronoUnit.MINUTES);
        Instant end1h = now.plus(70, ChronoUnit.MINUTES);
        List<AppointmentEntity> appts1h = appointmentRepository.findByStatusInAndStartDateTimeBetweenAndReminder1hSentFalse(
                List.of(AppointmentStatus.CREATED, AppointmentStatus.UPDATED), start1h, end1h
        );
        for (AppointmentEntity appt : appts1h) {
            sendReminder(appt, "in 1 hour");
            appt.setReminder1hSent(true);
            appointmentRepository.save(appt);
        }

        // 2. Process 1-Day Reminders (appointments starting in [23, 25] hours)
        Instant start1d = now.plus(23, ChronoUnit.HOURS);
        Instant end1d = now.plus(25, ChronoUnit.HOURS);
        List<AppointmentEntity> appts1d = appointmentRepository.findByStatusInAndStartDateTimeBetweenAndReminder1dSentFalse(
                List.of(AppointmentStatus.CREATED, AppointmentStatus.UPDATED), start1d, end1d
        );
        for (AppointmentEntity appt : appts1d) {
            sendReminder(appt, "tomorrow");
            appt.setReminder1dSent(true);
            appointmentRepository.save(appt);
        }

        // 3. Process 7-Day Reminders (appointments starting in [167, 169] hours)
        Instant start7d = now.plus(167, ChronoUnit.HOURS);
        Instant end7d = now.plus(169, ChronoUnit.HOURS);
        List<AppointmentEntity> appts7d = appointmentRepository.findByStatusInAndStartDateTimeBetweenAndReminder7dSentFalse(
                List.of(AppointmentStatus.CREATED, AppointmentStatus.UPDATED), start7d, end7d
        );
        for (AppointmentEntity appt : appts7d) {
            sendReminder(appt, "in 1 week");
            appt.setReminder7dSent(true);
            appointmentRepository.save(appt);
        }
    }

    private void sendReminder(AppointmentEntity appt, String timeframe) {
        String formattedDate = FORMATTER.format(appt.getStartDateTime());
        String doctorName = appt.getFromName() != null ? appt.getFromName() : "Doctor";
        String patientName = appt.getToName() != null ? appt.getToName() : "Patient";
        String description = appt.getNote() != null ? appt.getNote() : "-";

        String subject = "Reminder: Your appointment with Dr. " + doctorName + " is scheduled " + timeframe;
        String content = String.format("<p>Hi %s,</p><p>This is a reminder that you have an upcoming appointment with Dr. %s scheduled %s on %s.</p><p>Description: %s</p>",
                patientName, doctorName, timeframe, formattedDate, description);

        // In-app reminder
        webNotificationService.createReminder(
                appt.getToKey(), appt.getToType(),
                appt.getId().toString(), "Appointments",
                appt.getStartDateTime(), "Reminder",
                "Reminder: Upcoming appointment with Dr. " + doctorName + " " + timeframe
        );

        // Outbound email
        if (appt.getToEmail() != null && notificationPreferenceService.isNotificationEnabled(appt.getToKey(), appt.getToType(), "EMAIL")) {
            notificationServiceClient.sendAppointmentEmail(appt.getToEmail(), subject, content, appt.getId().toString(), "Reminder");
        }

        // Outbound push
        if (notificationPreferenceService.isNotificationEnabled(appt.getToKey(), appt.getToType(), "PUSH")) {
            notificationServiceClient.sendAppointmentPush(appt.getToKey(), "Appointment Reminder", "Your appointment with Dr. " + doctorName + " is " + timeframe, appt.getId().toString(), "Reminder");
        }
    }
}
