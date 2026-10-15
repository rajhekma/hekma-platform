package com.hekma.appointment.service;

import com.hekma.appointment.dto.ConflictCheckResponse;
import com.hekma.appointment.exception.ConflictException;
import com.hekma.appointment.repository.AppointmentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ConflictDetectionServiceTest {

    private AppointmentRepository appointmentRepository;
    private ConflictDetectionService conflictDetectionService;

    @BeforeEach
    void setUp() {
        appointmentRepository = mock(AppointmentRepository.class);
        conflictDetectionService = new ConflictDetectionService(appointmentRepository);
    }

    @Test
    void returnsNoConflictWhenNeitherUserIsBusy() {
        when(appointmentRepository.countConflictingAppointments(anyString(), anyString(), any(), any(), any()))
                .thenReturn(0L);

        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.plus(30, ChronoUnit.MINUTES);

        ConflictCheckResponse response = conflictDetectionService.checkConflicts(
                "doc-1", "doctor", "Dr. Smith",
                "pat-1", "patient", "John Doe",
                start, end, null
        );

        assertFalse(response.isHasConflict());
        assertEquals("No appointment conflicts found.", response.getMessage());
    }

    @Test
    void returnsConflictWhenDoctorIsBusy() {
        when(appointmentRepository.countConflictingAppointments(eq("doc-1"), eq("doctor"), any(), any(), any()))
                .thenReturn(1L);
        when(appointmentRepository.countConflictingAppointments(eq("pat-1"), eq("patient"), any(), any(), any()))
                .thenReturn(0L);

        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.plus(30, ChronoUnit.MINUTES);

        ConflictCheckResponse response = conflictDetectionService.checkConflicts(
                "doc-1", "doctor", "Dr. Smith",
                "pat-1", "patient", "John Doe",
                start, end, null
        );

        assertTrue(response.isHasConflict());
        assertTrue(response.getMessage().contains("Dr. Smith already has an appointment"));
        assertEquals("doc-1", response.getConflictingUser());
    }

    @Test
    void returnsConflictWhenBothUsersAreBusy() {
        when(appointmentRepository.countConflictingAppointments(anyString(), anyString(), any(), any(), any()))
                .thenReturn(1L);

        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.plus(30, ChronoUnit.MINUTES);

        ConflictCheckResponse response = conflictDetectionService.checkConflicts(
                "doc-1", "doctor", "Dr. Smith",
                "pat-1", "patient", "John Doe",
                start, end, null
        );

        assertTrue(response.isHasConflict());
        assertTrue(response.getMessage().contains("Both Dr. Smith and John Doe"));
        assertEquals("BOTH", response.getConflictingUser());
    }

    @Test
    void throwsConflictExceptionOnAssertNoConflict() {
        when(appointmentRepository.countConflictingAppointments(anyString(), anyString(), any(), any(), any()))
                .thenReturn(1L);

        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.plus(30, ChronoUnit.MINUTES);

        assertThrows(ConflictException.class, () ->
                conflictDetectionService.assertNoConflict(
                        "doc-1", "doctor", "Dr. Smith",
                        "pat-1", "patient", "John Doe",
                        start, end, null
                )
        );
    }

    @Test
    void throwsIllegalArgumentExceptionWhenStartIsAfterEnd() {
        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.minus(30, ChronoUnit.MINUTES);

        assertThrows(IllegalArgumentException.class, () ->
                conflictDetectionService.checkConflicts(
                        "doc-1", "doctor", "Dr. Smith",
                        "pat-1", "patient", "John Doe",
                        start, end, null
                )
        );
    }
}
