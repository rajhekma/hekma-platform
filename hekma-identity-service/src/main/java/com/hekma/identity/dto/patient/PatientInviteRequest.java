package com.hekma.identity.dto.patient;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Payload for inviting a patient to join a clinical trial / study (SPONSOR or SITE caller)")
public class PatientInviteRequest {

    @NotBlank(message = "Patient first name is required")
    @Size(min = 1, max = 100, message = "First name must be between 1 and 100 characters")
    @Schema(description = "Patient's first name", example = "Jane")
    private String firstName;

    @NotBlank(message = "Patient last name is required")
    @Size(min = 1, max = 100, message = "Last name must be between 1 and 100 characters")
    @Schema(description = "Patient's last name", example = "Doe")
    private String lastName;

    @NotBlank(message = "Patient email is required")
    @Email(message = "Email must be a valid email address")
    @Schema(description = "Patient's email address", example = "jane.doe@example.com")
    private String email;

    @Schema(description = "Patient's phone number (optional)", example = "+15551234567")
    private String phoneNumber;

    @Schema(description = "Target tenant for the patient: the inviter's tenant (default) or one of its sub-tenants")
    private java.util.UUID tenantId;

    @Schema(description = "SPONSOR/SITE user the patient is assigned to (default: the inviter). Must belong to the target "
            + "tenant or one of its ancestors, within the inviter's subtree.")
    private java.util.UUID assignedUserId;

    @Schema(description = "Associated clinical trial or study protocol ID", example = "STUDY-ONCOLOGY-01")
    private String clinicalStudyId;
}
