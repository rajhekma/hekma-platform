package com.hekma.identity.dto.otp;

import com.hekma.identity.domain.otp.VerificationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Response confirming OTP resend")
public class ResendOtpResponse {

    @Schema(description = "Active authentication attempt identifier", example = "550e8400-e29b-41d4-a716-446655440000")
    private UUID attemptId;

    @Schema(description = "Recipient phone number", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Recipient email address", example = "patient@hekma.com")
    private String email;

    @Schema(description = "Verification mode through which OTP was dispatched (PHONE, EMAIL)", example = "PHONE")
    private VerificationMode verificationMode;

    @Schema(description = "Current resend count for this attempt", example = "1")
    private int resendCount;

    @Schema(description = "Remaining resends allowed for this attempt (max 3)", example = "2")
    private int resendsRemaining;

    @Schema(description = "OTP expiration duration in seconds", example = "300")
    private long expiresInSeconds;

    @Schema(description = "Status message", example = "OTP has been resent successfully.")
    private String message;

    // Backward-compatibility alias
    public VerificationMode getChannel() {
        return verificationMode;
    }

    public void setChannel(VerificationMode channel) {
        this.verificationMode = channel;
    }
}
