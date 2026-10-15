package com.hekma.appointment.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.appointment.domain.AppointmentStatus;
import com.hekma.appointment.dto.AppointmentRequest;
import com.hekma.appointment.dto.AppointmentResponse;
import com.hekma.appointment.dto.ConflictCheckRequest;
import com.hekma.appointment.dto.ConflictCheckResponse;
import com.hekma.appointment.exception.ConflictException;
import com.hekma.appointment.exception.GlobalExceptionHandler;
import com.hekma.appointment.service.AppointmentService;
import com.hekma.appointment.service.ConflictDetectionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class AppointmentControllerTest {

    private MockMvc mockMvc;
    private AppointmentService appointmentService;
    private ConflictDetectionService conflictDetectionService;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        appointmentService = mock(AppointmentService.class);
        conflictDetectionService = mock(ConflictDetectionService.class);
        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new com.fasterxml.jackson.datatype.jsr310.JavaTimeModule());

        AppointmentController controller = new AppointmentController(appointmentService, conflictDetectionService);
        mockMvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new GlobalExceptionHandler(objectMapper))
                .build();
    }

    @Test
    void createAppointmentSuccess() throws Exception {
        UUID id = UUID.randomUUID();
        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.plus(30, ChronoUnit.MINUTES);

        AppointmentRequest request = AppointmentRequest.builder()
                .fromKey("doc-1")
                .fromType("doctor")
                .fromName("Dr. Smith")
                .fromEmail("smith@clinic.com")
                .toKey("pat-1")
                .toType("patient")
                .toName("John Doe")
                .toEmail("john@mail.com")
                .startDateTime(start)
                .endDateTime(end)
                .note("Regular checkup")
                .build();

        AppointmentResponse response = AppointmentResponse.builder()
                .id(id)
                .appointmentId(id.toString())
                .fromKey("doc-1")
                .toKey("pat-1")
                .status(AppointmentStatus.CREATED)
                .startDateTime(start)
                .endDateTime(end)
                .build();

        when(appointmentService.createAppointment(any(), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/appointments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(id.toString()))
                .andExpect(jsonPath("$.status").value("CREATED"));
    }

    @Test
    void createAppointmentReturns409WhenConflictOccurs() throws Exception {
        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.plus(30, ChronoUnit.MINUTES);

        AppointmentRequest request = AppointmentRequest.builder()
                .fromKey("doc-1")
                .fromType("doctor")
                .toKey("pat-1")
                .toType("patient")
                .startDateTime(start)
                .endDateTime(end)
                .build();

        when(appointmentService.createAppointment(any(), any()))
                .thenThrow(new ConflictException("Doctor already has an appointment during this time window."));

        mockMvc.perform(post("/api/v1/appointments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.error").value("Conflict"))
                .andExpect(jsonPath("$.message").value("Doctor already has an appointment during this time window."));
    }

    @Test
    void checkConflictsEndpointReturnsOk() throws Exception {
        Instant start = Instant.now().plus(1, ChronoUnit.DAYS);
        Instant end = start.plus(30, ChronoUnit.MINUTES);

        ConflictCheckRequest request = ConflictCheckRequest.builder()
                .user1Key("doc-1")
                .user1Type("doctor")
                .user2Key("pat-1")
                .user2Type("patient")
                .startDateTime(start)
                .endDateTime(end)
                .build();

        ConflictCheckResponse response = ConflictCheckResponse.builder()
                .hasConflict(false)
                .message("No appointment conflicts found.")
                .build();

        when(conflictDetectionService.checkConflicts(any(ConflictCheckRequest.class))).thenReturn(response);

        mockMvc.perform(post("/api/v1/appointments/check-conflicts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.hasConflict").value(false))
                .andExpect(jsonPath("$.message").value("No appointment conflicts found."));
    }
}
