package com.hekma.identity.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload for initiating password reset")
public class ForgotPasswordRequest {

    @Schema(description = "User registered email address", example = "admin@hekma.ai")
    private String email;

    @Schema(description = "User registered phone number in E.164 format", example = "+1234567890")
    private String phoneNumber;

    @Schema(description = "Universal identifier (email or phone)", example = "admin@hekma.ai")
    private String identifier;
}
