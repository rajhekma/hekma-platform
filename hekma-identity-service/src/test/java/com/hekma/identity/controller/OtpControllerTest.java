package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.otp.OtpPurpose;
import com.hekma.identity.dto.otp.ResendOtpRequest;
import com.hekma.identity.dto.otp.ResendOtpResponse;
import com.hekma.identity.dto.otp.SendOtpRequest;
import com.hekma.identity.dto.otp.SendOtpResponse;
import com.hekma.identity.dto.otp.VerifyOtpRequest;
import com.hekma.identity.dto.otp.VerifyOtpResponse;
import com.hekma.identity.exception.GlobalExceptionHandler;
import com.hekma.identity.exception.InvalidOtpException;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.exception.OtpExpiredException;
import com.hekma.identity.exception.OtpLockoutException;
import com.hekma.identity.exception.OtpResendLimitException;
import com.hekma.identity.exception.OtpVerificationLimitException;
import com.hekma.identity.service.OtpService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class OtpControllerTest {

    private MockMvc mockMvc;

    @Mock
    private OtpService otpService;

    @InjectMocks
    private OtpController otpController;

    private ObjectMapper objectMapper;

    private final UUID attemptId = UUID.randomUUID();
    private final String phone = "+1234567890";

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(otpController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
        objectMapper = new ObjectMapper();
    }

    // ==========================================
    // Send OTP Endpoint Tests
    // ==========================================

    @Test
    @DisplayName("POST /api/v1/auth/otp/send - 200 OK")
    void sendOtp_Success() throws Exception {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.LOGIN)
                .build();

        SendOtpResponse response = SendOtpResponse.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .expiresInSeconds(300)
                .message("OTP has been sent to your registered phone number.")
                .build();

        when(otpService.sendOtp(any(SendOtpRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/auth/otp/send")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.attemptId").value(attemptId.toString()))
                .andExpect(jsonPath("$.phoneNumber").value(phone))
                .andExpect(jsonPath("$.expiresInSeconds").value(300))
                .andExpect(jsonPath("$.message").value(containsString("OTP has been sent")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/send - 400 Bad Request when phone number is missing for PHONE verification mode")
    void sendOtp_ValidationFailure_BlankPhone() throws Exception {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber("")
                .build();

        when(otpService.sendOtp(any(SendOtpRequest.class), any()))
                .thenThrow(new IllegalArgumentException("Phone number is required when verification mode is PHONE"));

        mockMvc.perform(post("/api/v1/auth/otp/send")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(containsString("Phone number is required")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/send - 429 Too Many Requests when locked out")
    void sendOtp_Lockout_429() throws Exception {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.LOGIN)
                .build();

        when(otpService.sendOtp(any(SendOtpRequest.class), any()))
                .thenThrow(new OtpLockoutException("Your OTP limit is reached, please come back at 04:30 PM or after 30 mins"));

        mockMvc.perform(post("/api/v1/auth/otp/send")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.status").value(429))
                .andExpect(jsonPath("$.message").value(containsString("Your OTP limit is reached, please come back at")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/send - 401 Unauthorized if patient not registered")
    void sendOtp_PatientNotFound_401() throws Exception {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.LOGIN)
                .build();

        when(otpService.sendOtp(any(SendOtpRequest.class), any()))
                .thenThrow(new InvalidTokenException("No registered patient account found with phone number " + phone));

        mockMvc.perform(post("/api/v1/auth/otp/send")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401))
                .andExpect(jsonPath("$.message").value(containsString("No registered patient account found")));
    }

    // ==========================================
    // Resend OTP Endpoint Tests
    // ==========================================

    @Test
    @DisplayName("POST /api/v1/auth/otp/resend - 200 OK")
    void resendOtp_Success() throws Exception {
        ResendOtpRequest request = ResendOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .build();

        ResendOtpResponse response = ResendOtpResponse.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .resendCount(1)
                .resendsRemaining(2)
                .expiresInSeconds(300)
                .message("OTP has been resent successfully.")
                .build();

        when(otpService.resendOtp(any(ResendOtpRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/auth/otp/resend")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.attemptId").value(attemptId.toString()))
                .andExpect(jsonPath("$.resendCount").value(1))
                .andExpect(jsonPath("$.resendsRemaining").value(2))
                .andExpect(jsonPath("$.message").value(containsString("resent successfully")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/resend - 429 Too Many Requests when resend limit reached")
    void resendOtp_ResendLimitReached_429() throws Exception {
        ResendOtpRequest request = ResendOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .build();

        when(otpService.resendOtp(any(ResendOtpRequest.class), any()))
                .thenThrow(new OtpResendLimitException("Maximum OTP resend limit reached for this authentication attempt. Please initiate a new authentication attempt."));

        mockMvc.perform(post("/api/v1/auth/otp/resend")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.status").value(429))
                .andExpect(jsonPath("$.message").value(containsString("Maximum OTP resend limit reached")));
    }

    // ==========================================
    // Verify OTP Endpoint Tests
    // ==========================================

    @Test
    @DisplayName("POST /api/v1/auth/otp/verify - 200 OK")
    void verifyOtp_Success() throws Exception {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123456")
                .build();

        VerifyOtpResponse response = VerifyOtpResponse.builder()
                .verified(true)
                .attemptId(attemptId)
                .phoneNumber(phone)
                .firebaseCustomToken("mock-firebase-custom-token")
                .userId(UUID.randomUUID())
                .email("patient@example.com")
                .role(Role.PATIENT)
                .displayName("John Doe")
                .message("OTP verified successfully.")
                .build();

        when(otpService.verifyOtp(any(VerifyOtpRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/auth/otp/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.verified").value(true))
                .andExpect(jsonPath("$.firebaseCustomToken").value("mock-firebase-custom-token"))
                .andExpect(jsonPath("$.role").value("PATIENT"))
                .andExpect(jsonPath("$.message").value("OTP verified successfully."));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/verify - 400 Bad Request on invalid format")
    void verifyOtp_InvalidCodeFormat_400() throws Exception {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123") // Less than 6 digits
                .build();

        mockMvc.perform(post("/api/v1/auth/otp/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(containsString("Validation failed")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/verify - 400 Bad Request when expired")
    void verifyOtp_Expired_400() throws Exception {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123456")
                .build();

        when(otpService.verifyOtp(any(VerifyOtpRequest.class), any()))
                .thenThrow(new OtpExpiredException("OTP has expired. Please request a new OTP."));

        mockMvc.perform(post("/api/v1/auth/otp/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.message").value(containsString("OTP has expired")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/verify - 400 Bad Request when incorrect code")
    void verifyOtp_IncorrectCode_400() throws Exception {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("654321")
                .build();

        when(otpService.verifyOtp(any(VerifyOtpRequest.class), any()))
                .thenThrow(new InvalidOtpException("Invalid OTP code. 4 attempts remaining."));

        mockMvc.perform(post("/api/v1/auth/otp/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.message").value(containsString("4 attempts remaining")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/otp/verify - 400 Bad Request when max verification attempts exceeded")
    void verifyOtp_MaxAttemptsExceeded_400() throws Exception {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("654321")
                .build();

        when(otpService.verifyOtp(any(VerifyOtpRequest.class), any()))
                .thenThrow(new OtpVerificationLimitException("Maximum verification attempts exceeded. This OTP is now invalid. Please request a new OTP."));

        mockMvc.perform(post("/api/v1/auth/otp/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.message").value(containsString("Maximum verification attempts exceeded")));
    }
}
