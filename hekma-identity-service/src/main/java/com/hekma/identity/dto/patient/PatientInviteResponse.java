package com.hekma.identity.dto.patient;

import io.swagger.v3.oas.annotations.media.Schema;
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
@Schema(description = "Response returned when a patient is invited to a clinical trial")
public class PatientInviteResponse {

    @Schema(description = "Unique identifier of the staged patient user")
    private UUID patientId;

    @Schema(description = "Patient's invited email address")
    private String email;

    @Schema(description = "Generated invitation code / token")
    private String invitationCode;

    @Schema(description = "Tenant ID of the inviter's organization")
    private UUID tenantId;

    @Schema(description = "Tenant slug of the inviter's organization")
    private String tenantSlug;

    @Schema(description = "UUID of the SITE or SPONSOR user who sent the invite")
    private UUID assignedUserId;

    @Schema(description = "Informational status message")
    private String message;
}
