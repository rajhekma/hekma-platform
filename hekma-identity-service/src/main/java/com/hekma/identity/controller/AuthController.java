package com.hekma.identity.controller;

import com.hekma.identity.dto.ApiErrorResponse;
import com.hekma.identity.dto.LoginRequest;
import com.hekma.identity.dto.LoginResponse;
import com.hekma.identity.dto.RefreshTokenRequest;
import com.hekma.identity.dto.RefreshTokenResponse;
import com.hekma.identity.dto.RegisterRequest;
import com.hekma.identity.dto.RegisterResponse;
import com.hekma.identity.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
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
import com.hekma.identity.security.HekmaPrincipal;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.RestController;

@Slf4j
@RestController
@RequestMapping("/api/v1/auth")
@Tag(name = "Authentication", description = "Endpoints for user registration, authentication, token refresh, and OTP verification")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/register")
    @Operation(
            summary = "Register user with email and password",
            description = "Creates a user account in Firebase Auth, assigns custom claims (`role`), and persists the profile in PostgreSQL. " +
                    "**Allowed public roles**: `SITE`, `SPONSOR`, `PATIENT`. " +
                    "Attempts to self-register as `SYSTEM_ADMIN` or `ADMIN` are rejected with `400 Bad Request`."
    )
    @RequestBody(
            description = "User registration payload with credentials, target role, and display name",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = RegisterRequest.class),
                    examples = {
                            @ExampleObject(
                                    name = "Sponsor Registration",
                                    summary = "Register as a SPONSOR",
                                    value = "{\n  \"email\": \"sponsor@pharma-corp.com\",\n  \"password\": \"SecurePass123!\",\n  \"role\": \"SPONSOR\",\n  \"displayName\": \"Dr. Emily Watson\"\n}"
                            ),
                            @ExampleObject(
                                    name = "Site Investigator Registration",
                                    summary = "Register as a SITE investigator/staff",
                                    value = "{\n  \"email\": \"investigator@city-hospital.org\",\n  \"password\": \"SecurePass123!\",\n  \"role\": \"SITE\",\n  \"displayName\": \"Dr. Marcus Vance\"\n}"
                            ),
                            @ExampleObject(
                                    name = "Patient Registration",
                                    summary = "Register as a PATIENT",
                                    value = "{\n  \"email\": \"patient.smith@example.com\",\n  \"password\": \"SecurePass123!\",\n  \"role\": \"PATIENT\",\n  \"displayName\": \"Alice Smith\"\n}"
                            )
                    }
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "201",
                    description = "User successfully registered in Firebase Auth and PostgreSQL",
                    content = @Content(
                            schema = @Schema(implementation = RegisterResponse.class),
                            examples = @ExampleObject(
                                    name = "Success Response",
                                    value = "{\n  \"id\": \"7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6\",\n  \"firebaseUid\": \"fb-usr-987654321\",\n  \"email\": \"sponsor@pharma-corp.com\",\n  \"role\": \"SPONSOR\",\n  \"displayName\": \"Dr. Emily Watson\",\n  \"status\": \"ACTIVE\",\n  \"createdAt\": \"2026-09-28T12:00:00Z\",\n  \"message\": \"User registered successfully.\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Validation failure or disallowed role (e.g. attempting to self-register as SYSTEM_ADMIN or ADMIN)",
                    content = @Content(
                            schema = @Schema(implementation = ApiErrorResponse.class),
                            examples = @ExampleObject(
                                    name = "Disallowed Role Error",
                                    value = "{\n  \"status\": 400,\n  \"error\": \"Bad Request\",\n  \"message\": \"Role 'SYSTEM_ADMIN' is not permitted for public self-registration. Allowed roles are: SPONSOR, SITE, PATIENT.\",\n  \"timestamp\": \"2026-09-28T12:00:00Z\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "409",
                    description = "Email is already registered in PostgreSQL or Firebase",
                    content = @Content(
                            schema = @Schema(implementation = ApiErrorResponse.class),
                            examples = @ExampleObject(
                                    name = "Duplicate Email Error",
                                    value = "{\n  \"status\": 409,\n  \"error\": \"Conflict\",\n  \"message\": \"A user with email 'sponsor@pharma-corp.com' is already registered in the system.\",\n  \"timestamp\": \"2026-09-28T12:00:00Z\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "502",
                    description = "Firebase service communication error",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    public ResponseEntity<RegisterResponse> register(@Valid @org.springframework.web.bind.annotation.RequestBody RegisterRequest request,
                                                     HttpServletRequest httpRequest) {
        String clientIp = extractClientIp(httpRequest);
        RegisterResponse response = authService.register(request, clientIp);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PostMapping("/login")
    @Operation(
            summary = "Authenticate user and log in",
            description = "Authenticates user credentials against Firebase and PostgreSQL. " +
                    "<ul>" +
                    "<li>If the user is a <b>PATIENT</b> with 2FA enabled (`twoFactorEnabled = true`), an OTP is dispatched and `twoFactorRequired: true` is returned along with `otpAttemptId`. Authentication tokens will not be issued until the OTP is verified via `/api/v1/auth/otp/verify`.</li>" +
                    "<li>If the user is a <b>PATIENT</b> with 2FA disabled (default), direct login is granted (`twoFactorRequired: false`), returning JWT tokens and user details.</li>" +
                    "<li>For all other roles (<b>SYSTEM_ADMIN</b>, <b>ADMIN</b>, <b>SPONSOR</b>, <b>SITE</b>), direct login is granted immediately without 2FA (`twoFactorRequired: false`).</li>" +
                    "</ul>"
    )
    @RequestBody(
            description = "User login credentials payload",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = LoginRequest.class),
                    examples = {
                            @ExampleObject(
                                    name = "Login with Email",
                                    summary = "Sign in using email and password",
                                    value = "{\n  \"email\": \"patient.smith@example.com\",\n  \"password\": \"SecurePass123!\"\n}"
                            ),
                            @ExampleObject(
                                    name = "Login with Phone",
                                    summary = "Sign in using phone number and password",
                                    value = "{\n  \"phoneNumber\": \"+1234567890\",\n  \"password\": \"SecurePass123!\"\n}"
                            )
                    }
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "Login successful or 2FA OTP challenge initiated",
                    content = @Content(
                            schema = @Schema(implementation = LoginResponse.class),
                            examples = {
                                    @ExampleObject(
                                            name = "Direct Login Success",
                                            summary = "Direct login response (no 2FA)",
                                            value = "{\n  \"twoFactorRequired\": false,\n  \"twoFactorEnabled\": false,\n  \"idToken\": \"eyJhbGciOiJSUzI1NiIs...\",\n  \"refreshToken\": \"AMf-vBx...\",\n  \"tokenType\": \"Bearer\",\n  \"expiresIn\": 3600,\n  \"userId\": \"7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6\",\n  \"email\": \"sponsor@pharma-corp.com\",\n  \"role\": \"SPONSOR\",\n  \"displayName\": \"Dr. Emily Watson\",\n  \"status\": \"ACTIVE\",\n  \"message\": \"Login successful.\"\n}"
                                    ),
                                    @ExampleObject(
                                            name = "2FA Required Challenge",
                                            summary = "2FA challenge response (OTP required)",
                                            value = "{\n  \"twoFactorRequired\": true,\n  \"twoFactorEnabled\": true,\n  \"otpAttemptId\": \"550e8400-e29b-41d4-a716-446655440000\",\n  \"otpExpiresInSeconds\": 300,\n  \"verificationMode\": \"PHONE\",\n  \"userId\": \"7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6\",\n  \"phoneNumber\": \"+1234567890\",\n  \"role\": \"PATIENT\",\n  \"displayName\": \"Alice Smith\",\n  \"status\": \"ACTIVE\",\n  \"message\": \"Two-factor authentication required. An OTP has been sent to your registered phone number for verification.\"\n}"
                                    )
                            }
                    )
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Validation failure or missing credentials",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "401",
                    description = "Invalid email/phone or password",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "User account is suspended, inactive, or pending verification",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "502",
                    description = "Firebase service communication error",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    public ResponseEntity<LoginResponse> login(@Valid @org.springframework.web.bind.annotation.RequestBody LoginRequest request,
                                               HttpServletRequest httpRequest) {
        String clientIp = extractClientIp(httpRequest);
        LoginResponse response = authService.login(request, clientIp);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/refresh-token")
    @Operation(
            summary = "Refresh expired Firebase ID token",
            description = "Exchanges a valid OAuth2 refresh token for a new short-lived Firebase JWT ID token. " +
                    "Also verifies that the user account exists and is in ACTIVE status in the local database."
    )
    @RequestBody(
            description = "Refresh token payload",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = RefreshTokenRequest.class),
                    examples = @ExampleObject(
                            name = "Refresh Token Request",
                            value = "{\n  \"refreshToken\": \"AMf-vBx...\"\n}"
                    )
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "Token successfully refreshed",
                    content = @Content(
                            schema = @Schema(implementation = RefreshTokenResponse.class),
                            examples = @ExampleObject(
                                    name = "Success Response",
                                    value = "{\n  \"idToken\": \"eyJhbGciOiJSUzI1NiIs...\",\n  \"refreshToken\": \"AMf-vBx...\",\n  \"tokenType\": \"Bearer\",\n  \"expiresIn\": 3600,\n  \"firebaseUid\": \"fb-usr-987654321\",\n  \"email\": \"sponsor@pharma-corp.com\",\n  \"role\": \"SPONSOR\",\n  \"displayName\": \"Dr. Emily Watson\",\n  \"status\": \"ACTIVE\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Missing or blank refresh token",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "401",
                    description = "Invalid or expired refresh token",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "User account is suspended or inactive",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "502",
                    description = "Firebase service communication error",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    public ResponseEntity<RefreshTokenResponse> refreshToken(@Valid @org.springframework.web.bind.annotation.RequestBody RefreshTokenRequest request) {
        RefreshTokenResponse response = authService.refreshToken(request);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/forgot-password")
    @Operation(
            summary = "Initiate password reset",
            description = "Dispatches a 6-digit OTP verification code to the registered email or phone number"
    )
    public ResponseEntity<java.util.Map<String, String>> forgotPassword(
            @Valid @org.springframework.web.bind.annotation.RequestBody com.hekma.identity.dto.ForgotPasswordRequest request,
            HttpServletRequest servletRequest) {
        String clientIp = extractClientIp(servletRequest);
        String message = authService.forgotPassword(request, clientIp);
        return ResponseEntity.ok(java.util.Map.of("message", message, "status", "DISPATCHED"));
    }

    @PostMapping("/reset-password")
    @Operation(
            summary = "Reset password with verification code",
            description = "Verifies the 6-digit code and updates user password in Firebase Auth"
    )
    public ResponseEntity<java.util.Map<String, String>> resetPassword(
            @Valid @org.springframework.web.bind.annotation.RequestBody com.hekma.identity.dto.ResetPasswordRequest request,
            HttpServletRequest servletRequest) {
        authService.resetPassword(request, extractClientIp(servletRequest));
        return ResponseEntity.ok(java.util.Map.of("message", "Password successfully updated.", "status", "SUCCESS"));
    }

    @PostMapping("/register-tenant")
    @Operation(
            summary = "Register a new organization (public)",
            description = "Creates a new top-level SPONSOR or SITE tenant together with its owner user (role = tenant type) and sends " +
                    "a verification OTP. Tenant and owner stay PENDING_VERIFICATION until POST /api/v1/auth/otp/verify succeeds."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Organization registered; OTP sent",
                    content = @Content(schema = @Schema(implementation = com.hekma.identity.dto.tenant.RegisterTenantResponse.class))),
            @ApiResponse(responseCode = "400", description = "Validation error, invalid type or slug already taken",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "409", description = "Email or phone already registered",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<com.hekma.identity.dto.tenant.RegisterTenantResponse> registerTenant(
            @Valid @org.springframework.web.bind.annotation.RequestBody com.hekma.identity.dto.tenant.RegisterTenantRequest request,
            HttpServletRequest servletRequest) {
        return ResponseEntity.status(org.springframework.http.HttpStatus.CREATED)
                .body(authService.registerTenant(request, extractClientIp(servletRequest)));
    }

    @PostMapping("/change-password")
    @PreAuthorize("isAuthenticated()")
    @Operation(
            summary = "Change the authenticated user's password",
            description = "Validates the current password through Firebase, stores the new password in Firebase, " +
                    "revokes all existing sessions and returns a fresh ID token and refresh token."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Password changed; new tokens returned",
                    content = @Content(schema = @Schema(implementation = com.hekma.identity.dto.ChangePasswordResponse.class))),
            @ApiResponse(responseCode = "400", description = "New password violates the password policy or equals the current one",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "401", description = "Not authenticated, or current password is incorrect",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<com.hekma.identity.dto.ChangePasswordResponse> changePassword(
            @Valid @org.springframework.web.bind.annotation.RequestBody com.hekma.identity.dto.ChangePasswordRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(authService.changePassword(caller.userId(), request));
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
