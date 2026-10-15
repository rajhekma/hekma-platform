package com.hekma.identity.dto.otp;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload to resend an OTP for an active authentication attempt")
public class ResendOtpRequest {

    @Schema(description = "Active authentication attempt identifier", example = "550e8400-e29b-41d4-a716-446655440000")
    private UUID attemptId;

    @Schema(description = "User unique UUID in database (optional fallback if attemptId not available)", example = "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6")
    private UUID userId;

    @Schema(description = "Patient's registered phone number", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Patient's registered email address", example = "patient@hekma.com")
    private String email;
}
