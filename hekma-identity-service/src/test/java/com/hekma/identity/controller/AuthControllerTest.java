package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.dto.LoginRequest;
import com.hekma.identity.dto.LoginResponse;
import com.hekma.identity.dto.RefreshTokenRequest;
import com.hekma.identity.dto.RefreshTokenResponse;
import com.hekma.identity.dto.RegisterRequest;
import com.hekma.identity.dto.RegisterResponse;
import com.hekma.identity.exception.GlobalExceptionHandler;
import com.hekma.identity.exception.InvalidRoleException;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.exception.UserInactiveException;
import com.hekma.identity.service.AuthService;
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

import java.time.Instant;
import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class AuthControllerTest {

    private MockMvc mockMvc;

    @Mock
    private AuthService authService;

    @InjectMocks
    private AuthController authController;

    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(authController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .addFilters(new com.hekma.identity.config.TraceIdFilter())
                .build();

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
    }

    @Test
    @DisplayName("POST /api/v1/auth/register with valid PATIENT payload returns 201 Created and OTP attempt")
    void register_validRequest_returns201() throws Exception {
        UUID otpAttemptId = UUID.randomUUID();
        RegisterRequest request = RegisterRequest.builder()
                .email("patient@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .displayName("John Patient")
                .phoneNumber("+1234567890")
                .build();

        RegisterResponse response = RegisterResponse.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-uid-101")
                .email("patient@hekma.com")
                .role(Role.PATIENT)
                .displayName("John Patient")
                .phoneNumber("+1234567890")
                .status(UserStatus.PENDING_VERIFICATION)
                .otpAttemptId(otpAttemptId)
                .otpExpiresInSeconds(300L)
                .createdAt(Instant.now())
                .message("User registered successfully. An OTP has been sent to your phone number for verification.")
                .build();

        when(authService.register(any(RegisterRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/auth/register")
                        .header("X-Trace-Id", "trace-custom-999")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email").value("patient@hekma.com"))
                .andExpect(jsonPath("$.role").value("PATIENT"))
                .andExpect(jsonPath("$.firebaseUid").value("fb-uid-101"))
                .andExpect(jsonPath("$.phoneNumber").value("+1234567890"))
                .andExpect(jsonPath("$.status").value("PENDING_VERIFICATION"))
                .andExpect(jsonPath("$.otpAttemptId").value(otpAttemptId.toString()))
                .andExpect(jsonPath("$.otpExpiresInSeconds").value(300))
                .andExpect(jsonPath("$.traceId").value("trace-custom-999"));
    }

    @Test
    @DisplayName("POST /api/v1/auth/register with disallowed role SYSTEM_ADMIN returns 400 Bad Request")
    void register_systemAdminRole_returns400() throws Exception {
        RegisterRequest request = RegisterRequest.builder()
                .email("hacker@hekma.com")
                .password("Password123!")
                .role(Role.SYSTEM_ADMIN)
                .displayName("Sneaky User")
                .phoneNumber("+1234567890")
                .build();

        when(authService.register(any(RegisterRequest.class), any()))
                .thenThrow(new InvalidRoleException("Role 'SYSTEM_ADMIN' is not permitted for public self-registration. Allowed roles are: SPONSOR, SITE, PATIENT."));

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message", containsString("not permitted for public self-registration")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/register with duplicate email returns 409 Conflict")
    void register_duplicateEmail_returns409() throws Exception {
        RegisterRequest request = RegisterRequest.builder()
                .email("existing@hekma.com")
                .password("Password123!")
                .role(Role.SPONSOR)
                .phoneNumber("+1234567890")
                .build();

        when(authService.register(any(RegisterRequest.class), any()))
                .thenThrow(new UserAlreadyExistsException("A user with email 'existing@hekma.com' is already registered in the system."));

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.message", containsString("already registered")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/register with invalid email returns 400 Bad Request")
    void register_invalidEmail_returns400() throws Exception {
        RegisterRequest request = RegisterRequest.builder()
                .email("not-an-email")
                .password("Password123!")
                .role(Role.PATIENT)
                .phoneNumber("+1234567890")
                .build();

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("POST /api/v1/auth/register with short password returns 400 Bad Request")
    void register_shortPassword_returns400() throws Exception {
        RegisterRequest request = RegisterRequest.builder()
                .email("user@hekma.com")
                .password("123")
                .role(Role.SITE)
                .phoneNumber("+1234567890")
                .build();

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("POST /api/v1/auth/register with missing email and phone number returns 400 Bad Request")
    void register_missingEmailAndPhoneNumber_returns400() throws Exception {
        RegisterRequest request = RegisterRequest.builder()
                .password("Password123!")
                .role(Role.PATIENT)
                .build();

        when(authService.register(any(RegisterRequest.class), any()))
                .thenThrow(new IllegalArgumentException("At least one of email or phone number is required for registration."));

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("At least one of email or phone number is required for registration."));
    }

    @Test
    @DisplayName("POST /api/v1/auth/refresh-token with valid token returns 200 OK")
    void refreshToken_validToken_returns200() throws Exception {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("valid-refresh-token-xyz")
                .build();

        RefreshTokenResponse response = RefreshTokenResponse.builder()
                .idToken("new-id-token-abc")
                .refreshToken("new-refresh-token-xyz")
                .tokenType("Bearer")
                .expiresIn(3600L)
                .firebaseUid("fb-uid-123")
                .email("user@example.com")
                .role(Role.PATIENT)
                .displayName("Sarah Connor")
                .status(UserStatus.ACTIVE)
                .build();

        when(authService.refreshToken(any(RefreshTokenRequest.class))).thenReturn(response);

        mockMvc.perform(post("/api/v1/auth/refresh-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.idToken").value("new-id-token-abc"))
                .andExpect(jsonPath("$.refreshToken").value("new-refresh-token-xyz"))
                .andExpect(jsonPath("$.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.expiresIn").value(3600))
                .andExpect(jsonPath("$.role").value("PATIENT"))
                .andExpect(jsonPath("$.email").value("user@example.com"))
                .andExpect(jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    @DisplayName("POST /api/v1/auth/refresh-token with blank token returns 400 Bad Request")
    void refreshToken_blankToken_returns400() throws Exception {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("")
                .build();

        mockMvc.perform(post("/api/v1/auth/refresh-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("POST /api/v1/auth/refresh-token with invalid/expired token returns 401 Unauthorized")
    void refreshToken_invalidToken_returns401() throws Exception {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("expired-token")
                .build();

        when(authService.refreshToken(any(RefreshTokenRequest.class)))
                .thenThrow(new InvalidTokenException("The refresh token is invalid or expired. Please authenticate again."));

        mockMvc.perform(post("/api/v1/auth/refresh-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401))
                .andExpect(jsonPath("$.message").value(containsString("invalid or expired")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/refresh-token for suspended user returns 403 Forbidden")
    void refreshToken_suspendedUser_returns403() throws Exception {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("valid-token-suspended-user")
                .build();

        when(authService.refreshToken(any(RefreshTokenRequest.class)))
                .thenThrow(new UserInactiveException("User account is suspended. Authentication denied."));

        mockMvc.perform(post("/api/v1/auth/refresh-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status").value(403))
                .andExpect(jsonPath("$.message").value(containsString("User account is suspended")));
    }

    // ==========================================
    // POST /api/v1/auth/login
    // ==========================================

    @Test
    @DisplayName("POST /api/v1/auth/login direct login returns 200 OK and auth tokens")
    void login_directLogin_returns200AndTokens() throws Exception {
        LoginRequest request = LoginRequest.builder()
                .email("sponsor@pharma-corp.com")
                .password("SecurePass123!")
                .build();

        LoginResponse response = LoginResponse.builder()
                .twoFactorRequired(false)
                .twoFactorEnabled(false)
                .idToken("mock-jwt-id-token")
                .refreshToken("mock-refresh-token")
                .tokenType("Bearer")
                .expiresIn(3600L)
                .userId(UUID.randomUUID())
                .email("sponsor@pharma-corp.com")
                .role(Role.SPONSOR)
                .status(UserStatus.ACTIVE)
                .message("Login successful.")
                .build();

        when(authService.login(any(LoginRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.twoFactorRequired").value(false))
                .andExpect(jsonPath("$.idToken").value("mock-jwt-id-token"))
                .andExpect(jsonPath("$.refreshToken").value("mock-refresh-token"))
                .andExpect(jsonPath("$.email").value("sponsor@pharma-corp.com"))
                .andExpect(jsonPath("$.role").value("SPONSOR"))
                .andExpect(jsonPath("$.message").value("Login successful."));
    }

    @Test
    @DisplayName("POST /api/v1/auth/login with 2FA required returns 200 OK and otpAttemptId")
    void login_twoFactorRequired_returns200AndOtpAttempt() throws Exception {
        UUID otpAttemptId = UUID.randomUUID();
        LoginRequest request = LoginRequest.builder()
                .email("patient@hekma.com")
                .password("SecurePass123!")
                .build();

        LoginResponse response = LoginResponse.builder()
                .twoFactorRequired(true)
                .twoFactorEnabled(true)
                .otpAttemptId(otpAttemptId)
                .otpExpiresInSeconds(300L)
                .userId(UUID.randomUUID())
                .email("patient@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .message("Two-factor authentication required. An OTP has been sent for verification.")
                .build();

        when(authService.login(any(LoginRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.twoFactorRequired").value(true))
                .andExpect(jsonPath("$.twoFactorEnabled").value(true))
                .andExpect(jsonPath("$.otpAttemptId").value(otpAttemptId.toString()))
                .andExpect(jsonPath("$.otpExpiresInSeconds").value(300))
                .andExpect(jsonPath("$.idToken").doesNotExist())
                .andExpect(jsonPath("$.message").value(containsString("Two-factor authentication required")));
    }

    @Test
    @DisplayName("POST /api/v1/auth/login with blank password returns 400 Bad Request")
    void login_blankPassword_returns400() throws Exception {
        LoginRequest request = LoginRequest.builder()
                .email("patient@hekma.com")
                .password("")
                .build();

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("POST /api/v1/auth/login with invalid credentials returns 401 Unauthorized")
    void login_invalidCredentials_returns401() throws Exception {
        LoginRequest request = LoginRequest.builder()
                .email("patient@hekma.com")
                .password("WrongPassword123!")
                .build();

        when(authService.login(any(LoginRequest.class), any()))
                .thenThrow(new InvalidTokenException("Invalid email/phone or password."));

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401))
                .andExpect(jsonPath("$.message").value("Invalid email/phone or password."));
    }
}
