package com.hekma.identity.controller;

import com.hekma.identity.dto.ApiErrorResponse;
import com.hekma.identity.dto.otp.ResendOtpRequest;
import com.hekma.identity.dto.otp.ResendOtpResponse;
import com.hekma.identity.dto.otp.SendOtpRequest;
import com.hekma.identity.dto.otp.SendOtpResponse;
import com.hekma.identity.dto.otp.VerifyOtpRequest;
import com.hekma.identity.dto.otp.VerifyOtpResponse;
import com.hekma.identity.service.OtpService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth/otp")
@Tag(name = "Authentication", description = "Endpoints for user registration, authentication, token refresh, and OTP verification")
public class OtpController {

    private final OtpService otpService;

    public OtpController(OtpService otpService) {
        this.otpService = otpService;
    }

    @PostMapping("/send")
    @Operation(
            summary = "Generate and send OTP",
            description = "Generates a 6-digit numeric OTP valid for 5 minutes and delegates SMS transmission to hekma-notification-service. " +
                    "Enforces rate limiting (max 5 OTPs per hour per phone number). " +
                    "If the limit is reached, a 30-minute lockout is triggered."
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "OTP generated and dispatched successfully",
                    content = @Content(schema = @Schema(implementation = SendOtpResponse.class))),
            @ApiResponse(responseCode = "400", description = "Validation failed for request payload",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "401", description = "No patient account found for provided phone number (LOGIN / RE_AUTHENTICATION)",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "403", description = "Patient account is inactive",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "429", description = "Rate limit reached (lockout triggered for 30 minutes)",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<SendOtpResponse> sendOtp(
            @org.springframework.web.bind.annotation.RequestBody @Valid SendOtpRequest request,
            HttpServletRequest servletRequest) {
        String clientIp = extractClientIp(servletRequest);
        SendOtpResponse response = otpService.sendOtp(request, clientIp);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/resend")
    @Operation(
            summary = "Resend OTP",
            description = "Resends a new OTP for an active authentication attempt. A maximum of 3 resends are allowed per attempt. " +
                    "Resends reset the OTP validity to 5 minutes and count towards the hourly 5-request limit."
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "OTP resent successfully",
                    content = @Content(schema = @Schema(implementation = ResendOtpResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid request or attempt already verified",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "401", description = "Attempt ID not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "429", description = "Resend limit (max 3) reached or hourly limit reached",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<ResendOtpResponse> resendOtp(
            @org.springframework.web.bind.annotation.RequestBody @Valid ResendOtpRequest request,
            HttpServletRequest servletRequest) {
        String clientIp = extractClientIp(servletRequest);
        ResendOtpResponse response = otpService.resendOtp(request, clientIp);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/verify")
    @Operation(
            summary = "Verify OTP code",
            description = "Verifies the 6-digit OTP code. Allows a maximum of 5 attempts. " +
                    "If correct, sets the attempt to VERIFIED and returns authentication credentials (including Firebase custom token for patient login). " +
                    "If incorrect 5 times, invalidates the OTP requiring a new generation."
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "OTP verified successfully",
                    content = @Content(schema = @Schema(implementation = VerifyOtpResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid OTP code, expired OTP, or maximum attempts exceeded",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "401", description = "Attempt ID not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<VerifyOtpResponse> verifyOtp(
            @org.springframework.web.bind.annotation.RequestBody @Valid VerifyOtpRequest request,
            HttpServletRequest servletRequest) {
        String clientIp = extractClientIp(servletRequest);
        VerifyOtpResponse response = otpService.verifyOtp(request, clientIp);
        return ResponseEntity.ok(response);
    }

    private String extractClientIp(HttpServletRequest request) {
        if (request == null) {
            return "unknown";
        }
        String xfHeader = request.getHeader("X-Forwarded-For");
        if (xfHeader != null && !xfHeader.isBlank()) {
            return xfHeader.split(",")[0].trim();
        }
        return request.getRemoteAddr() != null ? request.getRemoteAddr() : "unknown";
    }
}
