package com.hekma.appointment.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Payload for scheduling or updating an appointment")
public class AppointmentRequest {

    @NotBlank(message = "fromKey is required")
    @Schema(description = "Identifier of the organizer / doctor / staff", example = "usr-doc-123")
    private String fromKey;

    @NotBlank(message = "fromType is required")
    @Schema(description = "Type of the organizer (e.g. doctor, staff, site)", example = "doctor")
    private String fromType;

    @Schema(description = "Name of the organizer", example = "Dr. Sarah Smith")
    private String fromName;

    @Schema(description = "Email of the organizer", example = "sarah.smith@clinic.com")
    private String fromEmail;

    @NotBlank(message = "toKey is required")
    @Schema(description = "Identifier of the participant / patient", example = "usr-pat-456")
    private String toKey;

    @NotBlank(message = "toType is required")
    @Schema(description = "Type of the participant (e.g. patient)", example = "patient")
    private String toType;

    @Schema(description = "Name of the participant", example = "John Doe")
    private String toName;

    @Schema(description = "Email of the participant", example = "john.doe@mail.com")
    private String toEmail;

    @NotNull(message = "startDateTime is required")
    @Schema(description = "Start timestamp in UTC", example = "2026-10-20T10:00:00Z")
    private Instant startDateTime;

    @NotNull(message = "endDateTime is required")
    @Schema(description = "End timestamp in UTC", example = "2026-10-20T10:30:00Z")
    private Instant endDateTime;

    @Schema(description = "Appointment note or clinical description", example = "Initial protocol screening assessment")
    private String note;

    @Schema(description = "Custom email subject", example = "Clinical Protocol Consultation")
    private String mailSubject;

    @Schema(description = "Custom email body for patient")
    private String mailText;

    @Schema(description = "Custom email body for doctor/staff")
    private String docMailText;

    @Schema(description = "Telehealth / navigation link for patient", example = "https://meet.hekma.ai/room-123")
    private String navLink;

    @Schema(description = "Telehealth / navigation link for doctor", example = "https://meet.hekma.ai/room-123-host")
    private String docNavLink;

    @Schema(description = "Optional study, site, or visit reference ID", example = "STUDY-2026-001")
    private String reference;
}
