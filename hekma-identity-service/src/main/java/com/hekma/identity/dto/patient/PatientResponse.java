package com.hekma.identity.dto.patient;

import com.hekma.identity.domain.UserStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Detailed patient profile and clinical assignment response")
public class PatientResponse {

    @Schema(description = "Patient user UUID")
    private UUID id;

    @Schema(description = "Patient detail record UUID")
    private UUID detailId;

    @Schema(description = "Patient email address")
    private String email;

    @Schema(description = "Full display name")
    private String displayName;

    @Schema(description = "Patient's first name")
    private String firstName;

    @Schema(description = "Patient's last name")
    private String lastName;

    @Schema(description = "Patient's phone number")
    private String phoneNumber;

    @Schema(description = "User lifecycle status (ACTIVE, INACTIVE, PENDING_VERIFICATION, SUSPENDED)")
    private UserStatus status;

    @Schema(description = "Whether the user account is active")
    private Boolean isActive;

    @Schema(description = "Associated tenant UUID")
    private UUID tenantId;

    @Schema(description = "Associated tenant slug")
    private String tenantSlug;

    @Schema(description = "UUID of the mapped SITE or SPONSOR investigator")
    private UUID assignedUserId;

    @Schema(description = "Display name of the mapped investigator")
    private String assignedUserName;

    @Schema(description = "Invitation code used (if invited)")
    private String invitationCode;

    @Schema(description = "Terms and conditions accepted flag")
    private Boolean termsAccepted;

    @Schema(description = "Privacy policy accepted flag")
    private Boolean privacyPolicyAccepted;

    @Schema(description = "Health data processing consent accepted flag")
    private Boolean healthDataConsentAccepted;

    @Schema(description = "Timestamp when regulatory consents were granted")
    private Instant consentedAt;

    @Schema(description = "Patient profile creation timestamp")
    private Instant createdAt;

    @Schema(description = "Informational status message")
    private String message;
}
