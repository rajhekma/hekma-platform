package com.hekma.identity.dto.otp;

import com.hekma.identity.domain.otp.OtpPurpose;
import com.hekma.identity.domain.otp.VerificationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload to initiate OTP generation and dispatch")
public class SendOtpRequest {

    @Schema(description = "Patient's registered phone number in E.164 format", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Patient's registered email address", example = "patient@hekma.com")
    private String email;

    @Builder.Default
    @Schema(description = "Verification mode for OTP (PHONE, EMAIL)", example = "PHONE")
    private VerificationMode verificationMode = VerificationMode.PHONE;

    @Builder.Default
    @Schema(description = "Authentication purpose for OTP", example = "LOGIN")
    private OtpPurpose purpose = OtpPurpose.LOGIN;

    // Backward-compatibility alias
    public VerificationMode getChannel() {
        return verificationMode;
    }

    public void setChannel(VerificationMode channel) {
        this.verificationMode = channel;
    }
}
