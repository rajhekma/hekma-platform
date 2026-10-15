package com.hekma.identity.dto.patient;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Payload for reassigning a patient to a SITE or SPONSOR investigator")
public class PatientAssignRequest {

    @NotNull(message = "Assigned user ID is required")
    @Schema(description = "UUID of the target SITE or SPONSOR user to assign this patient to", example = "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6")
    private UUID assignedUserId;
}
