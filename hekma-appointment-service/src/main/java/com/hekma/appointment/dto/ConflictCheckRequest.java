package com.hekma.appointment.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Payload to test whether a time slot has calendar conflicts")
public class ConflictCheckRequest {

    @NotBlank(message = "user1Key is required")
    private String user1Key;

    @NotBlank(message = "user1Type is required")
    private String user1Type;

    private String user1Name;

    @NotBlank(message = "user2Key is required")
    private String user2Key;

    @NotBlank(message = "user2Type is required")
    private String user2Type;

    private String user2Name;

    @NotNull(message = "startDateTime is required")
    private Instant startDateTime;

    @NotNull(message = "endDateTime is required")
    private Instant endDateTime;

    private UUID appointmentIdToExclude;
}
