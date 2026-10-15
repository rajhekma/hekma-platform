package com.hekma.appointment.scheduler;

import com.hekma.appointment.domain.AppointmentEntity;
import com.hekma.appointment.domain.AppointmentStatus;
import com.hekma.appointment.notification.NotificationServiceClient;
import com.hekma.appointment.repository.AppointmentRepository;
import com.hekma.appointment.service.NotificationPreferenceService;
import com.hekma.appointment.service.WebNotificationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class AppointmentReminderSchedulerTest {

    private AppointmentRepository appointmentRepository;
    private NotificationServiceClient notificationServiceClient;
    private NotificationPreferenceService notificationPreferenceService;
    private WebNotificationService webNotificationService;
    private AppointmentReminderScheduler scheduler;

    @BeforeEach
    void setUp() {
        appointmentRepository = mock(AppointmentRepository.class);
        notificationServiceClient = mock(NotificationServiceClient.class);
        notificationPreferenceService = mock(NotificationPreferenceService.class);
        webNotificationService = mock(WebNotificationService.class);

        when(notificationPreferenceService.isNotificationEnabled(any(), any(), eq("EMAIL"))).thenReturn(true);
        when(notificationPreferenceService.isNotificationEnabled(any(), any(), eq("PUSH"))).thenReturn(true);

        scheduler = new AppointmentReminderScheduler(
                appointmentRepository,
                notificationServiceClient,
                notificationPreferenceService,
                webNotificationService
        );
    }

    @Test
    void processes1HourRemindersSuccessfully() {
        AppointmentEntity entity = AppointmentEntity.builder()
                .id(UUID.randomUUID())
                .fromKey("doc-1")
                .fromName("Dr. Smith")
                .toKey("pat-1")
                .toName("John Doe")
                .toEmail("john@mail.com")
                .startDateTime(Instant.now().plus(60, ChronoUnit.MINUTES))
                .endDateTime(Instant.now().plus(90, ChronoUnit.MINUTES))
                .status(AppointmentStatus.CREATED)
                .reminder1hSent(false)
                .build();

        when(appointmentRepository.findByStatusInAndStartDateTimeBetweenAndReminder1hSentFalse(any(), any(), any()))
                .thenReturn(List.of(entity));

        scheduler.processReminders();

        assertTrue(entity.isReminder1hSent());
        verify(appointmentRepository, times(1)).save(entity);
        verify(notificationServiceClient, times(1)).sendAppointmentEmail(eq("john@mail.com"), anyString(), anyString(), anyString(), eq("Reminder"));
        verify(webNotificationService, times(1)).createReminder(any(), any(), any(), any(), any(), eq("Reminder"), any());
    }
}
