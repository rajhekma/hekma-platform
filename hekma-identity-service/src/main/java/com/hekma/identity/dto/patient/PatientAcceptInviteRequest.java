package com.hekma.identity.dto.patient;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.AssertTrue;
import com.hekma.identity.validation.StrongPassword;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
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
@Schema(description = "Payload for accepting an invitation and activating a patient account (Public)")
public class PatientAcceptInviteRequest {

    @NotBlank(message = "Invitation token/code is required")
    @Schema(description = "Invitation code or token received via email", example = "INV-7X9Q2Z-MayoClinic")
    private String invitationToken;

    @NotBlank(message = "Password is required")
    @StrongPassword
    @Schema(description = "Account password to set", example = "SecurePassword123!")
    private String password;

    @NotNull(message = "Terms acceptance is mandatory")
    @AssertTrue(message = "Terms and Conditions must be accepted")
    @Schema(description = "Consent to Hekma Platform Terms and Conditions", example = "true")
    private Boolean termsAccepted;

    @NotNull(message = "Privacy Policy acceptance is mandatory")
    @AssertTrue(message = "Privacy Policy must be accepted")
    @Schema(description = "Consent to Hekma Privacy Policy", example = "true")
    private Boolean privacyPolicyAccepted;

    @NotNull(message = "Health data consent acceptance is mandatory")
    @AssertTrue(message = "Health data processing consent must be accepted")
    @Schema(description = "Regulatory HIPAA/GDPR health data processing consent", example = "true")
    private Boolean healthDataConsentAccepted;
}
