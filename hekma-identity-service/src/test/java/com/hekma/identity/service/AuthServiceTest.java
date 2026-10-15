package com.hekma.identity.service;

import com.hekma.identity.dto.ChangePasswordResponse;
import com.hekma.identity.dto.ChangePasswordRequest;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import org.mockito.InOrder;
import com.hekma.identity.exception.InvalidOtpException;
import com.hekma.identity.dto.ForgotPasswordRequest;
import com.hekma.identity.dto.ResetPasswordRequest;
import com.hekma.identity.security.AuthEmails;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.OtpPurpose;
import com.hekma.identity.domain.otp.VerificationMode;
import com.hekma.identity.dto.InviteAdminRequest;
import com.hekma.identity.dto.LoginRequest;
import com.hekma.identity.dto.LoginResponse;
import com.hekma.identity.dto.RefreshTokenRequest;
import com.hekma.identity.dto.RefreshTokenResponse;
import com.hekma.identity.dto.RegisterRequest;
import com.hekma.identity.dto.RegisterResponse;
import com.hekma.identity.dto.otp.SendOtpRequest;
import com.hekma.identity.dto.otp.SendOtpResponse;
import com.hekma.identity.exception.InvalidRoleException;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.exception.UserInactiveException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseSignInResponse;
import com.hekma.identity.firebase.FirebaseTokenRefreshResponse;
import com.hekma.identity.firebase.FirebaseUserDto;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

    @Mock
    private UserRepository userRepository;

    @Mock
    private AuthorityService authorityService;

    @Mock
    private AuditService auditService;

    @Mock
    private FirebaseService firebaseService;

    @Mock
    private OtpService otpService;

    @Mock
    private NotificationServiceClient notificationServiceClient;

    @Mock
    private com.hekma.identity.repository.TenantRepository tenantRepository;

    @Mock
    private com.hekma.identity.repository.PatientDetailRepository patientDetailRepository;

    @Mock
    private com.hekma.identity.service.RoleAuthorityService roleAuthorityService;

    @InjectMocks
    private AuthService authService;

    private UserEntity sampleEntity;
    private com.hekma.identity.domain.TenantEntity defaultTenant;

    @BeforeEach
    void setUp() {
        defaultTenant = com.hekma.identity.domain.TenantEntity.builder()
                .id(UUID.fromString("00000000-0000-0000-0000-000000000001"))
                .name("Default Organization")
                .slug("default-tenant")
                .defaultTenant(true)
                .status(com.hekma.identity.domain.TenantStatus.ACTIVE)
                .build();
        lenient().when(tenantRepository.findByDefaultTenantTrue()).thenReturn(Optional.of(defaultTenant));
        lenient().when(tenantRepository.findBySlug("default-tenant")).thenReturn(Optional.of(defaultTenant));

        sampleEntity = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-uid-12345")
                .email("test@hekma.com")
                .role(Role.PATIENT)
                .displayName("Test User")
                .status(UserStatus.ACTIVE)
                .tenant(defaultTenant)
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();
    }


    @ParameterizedTest
    @EnumSource(value = Role.class, names = {"PATIENT"})
    @DisplayName("Public registration succeeds for PATIENT and dispatches OTP")
    void register_allowedRoles_success(Role role) {
        UUID otpAttemptId = UUID.randomUUID();
        RegisterRequest request = RegisterRequest.builder()
                .email("user@hekma.com")
                .password("Password123!")
                .role(role)
                .displayName("Valid User")
                .phoneNumber("+1234567890")
                .build();

        when(userRepository.existsByEmail("user@hekma.com")).thenReturn(false);
        when(userRepository.existsByPhoneNumber("+1234567890")).thenReturn(false);
        when(firebaseService.getUserByEmail("user@hekma.com")).thenReturn(Optional.empty());

        FirebaseUserDto fbDto = FirebaseUserDto.builder()
                .uid("fb-uid-test")
                .email("user@hekma.com")
                .displayName("Valid User")
                .role(role)
                .build();
        when(firebaseService.createUser("user@hekma.com", "Password123!", "Valid User", role)).thenReturn(fbDto);

        UserEntity savedEntity = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-uid-test")
                .email("user@hekma.com")
                .role(role)
                .displayName("Valid User")
                .phoneNumber("+1234567890")
                .status(UserStatus.PENDING_VERIFICATION)
                .createdAt(Instant.now())
                .build();
        when(userRepository.save(any(UserEntity.class))).thenReturn(savedEntity);

        SendOtpResponse otpResponse = SendOtpResponse.builder()
                .attemptId(otpAttemptId)
                .phoneNumber("+1234567890")
                .expiresInSeconds(300L)
                .message("OTP has been sent to your registered phone number.")
                .build();
        when(otpService.sendOtp(any(SendOtpRequest.class), any())).thenReturn(otpResponse);

        RegisterResponse response = authService.register(request);

        assertThat(response).isNotNull();
        assertThat(response.getEmail()).isEqualTo("user@hekma.com");
        assertThat(response.getRole()).isEqualTo(role);
        assertThat(response.getFirebaseUid()).isEqualTo("fb-uid-test");
        assertThat(response.getPhoneNumber()).isEqualTo("+1234567890");
        assertThat(response.getStatus()).isEqualTo(UserStatus.PENDING_VERIFICATION);
        assertThat(response.getOtpAttemptId()).isEqualTo(otpAttemptId);
        assertThat(response.getOtpExpiresInSeconds()).isEqualTo(300L);
        verify(firebaseService).createUser("user@hekma.com", "Password123!", "Valid User", role);
        verify(userRepository).save(any(UserEntity.class));
        verify(otpService).sendOtp(any(SendOtpRequest.class), any());
        verify(notificationServiceClient).sendWelcomeEmail(eq("user@hekma.com"), eq("Valid User"));
        verify(notificationServiceClient).sendWelcomeInApp(eq(savedEntity.getId()), eq("Valid User"));
    }

    @ParameterizedTest
    @EnumSource(value = Role.class, names = {"SYSTEM_ADMIN", "ADMIN"})
    @DisplayName("Public registration throws InvalidRoleException for restricted roles: SYSTEM_ADMIN, ADMIN")
    void register_restrictedRoles_throwsInvalidRoleException(Role restrictedRole) {
        RegisterRequest request = RegisterRequest.builder()
                .email("admin@hekma.com")
                .password("Password123!")
                .role(restrictedRole)
                .displayName("Restricted Role Attempt")
                .phoneNumber("+1234567890")
                .build();

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(InvalidRoleException.class)
                .hasMessageContaining("is not permitted for public self-registration");

        verifyNoInteractions(firebaseService);
        verifyNoInteractions(userRepository);
        verifyNoInteractions(otpService);
    }

    @Test
    @DisplayName("Public registration throws UserAlreadyExistsException when email exists in database")
    void register_duplicateEmailInDb_throwsException() {
        RegisterRequest request = RegisterRequest.builder()
                .email("existing@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .phoneNumber("+1234567890")
                .build();

        when(userRepository.existsByEmail("existing@hekma.com")).thenReturn(true);

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(UserAlreadyExistsException.class)
                .hasMessageContaining("already registered");

        verify(firebaseService, never()).createUser(anyString(), anyString(), anyString(), any());
        verifyNoInteractions(otpService);
    }

    @Test
    @DisplayName("Public registration throws UserAlreadyExistsException when phone number exists in database")
    void register_duplicatePhoneInDb_throwsException() {
        RegisterRequest request = RegisterRequest.builder()
                .email("unique@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .phoneNumber("+1999888777")
                .build();

        when(userRepository.existsByEmail("unique@hekma.com")).thenReturn(false);
        when(userRepository.existsByPhoneNumber("+1999888777")).thenReturn(true);

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(UserAlreadyExistsException.class)
                .hasMessageContaining("phone number '+1999888777' is already registered");

        verify(firebaseService, never()).createUser(anyString(), anyString(), anyString(), any());
        verifyNoInteractions(otpService);
    }

    @Test
    @DisplayName("Public registration throws UserAlreadyExistsException when email exists in Firebase")
    void register_duplicateEmailInFirebase_throwsException() {
        RegisterRequest request = RegisterRequest.builder()
                .email("firebase.exists@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .phoneNumber("+1234567890")
                .build();

        when(userRepository.existsByEmail("firebase.exists@hekma.com")).thenReturn(false);
        when(userRepository.existsByPhoneNumber("+1234567890")).thenReturn(false);
        when(firebaseService.getUserByEmail("firebase.exists@hekma.com"))
                .thenReturn(Optional.of(FirebaseUserDto.builder().uid("fb-99").build()));

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(UserAlreadyExistsException.class)
                .hasMessageContaining("already exists in Firebase");

        verify(firebaseService, never()).createUser(anyString(), anyString(), anyString(), any());
        verifyNoInteractions(otpService);
    }

    @Test
    @DisplayName("Compensating rollback deletes Firebase user when database persistence fails")
    void register_databaseError_triggersCompensatingRollback() {
        RegisterRequest request = RegisterRequest.builder()
                .email("rollback@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .phoneNumber("+1234567890")
                .build();

        when(userRepository.existsByEmail("rollback@hekma.com")).thenReturn(false);
        when(userRepository.existsByPhoneNumber("+1234567890")).thenReturn(false);
        when(firebaseService.getUserByEmail("rollback@hekma.com")).thenReturn(Optional.empty());

        FirebaseUserDto fbDto = FirebaseUserDto.builder()
                .uid("fb-rollback-id")
                .email("rollback@hekma.com")
                .role(Role.PATIENT)
                .build();
        when(firebaseService.createUser(eq("rollback@hekma.com"), eq("Password123!"), any(), eq(Role.PATIENT)))
                .thenReturn(fbDto);

        when(userRepository.save(any(UserEntity.class))).thenThrow(new RuntimeException("DB Connection Timeout"));

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("DB Connection Timeout");

        verify(firebaseService).deleteUser("fb-rollback-id");
        verifyNoInteractions(otpService);
    }

    @Test
    @DisplayName("Compensating rollback deletes DB user and Firebase user when OTP send fails")
    void register_otpSendFailure_triggersCompensatingRollback() {
        RegisterRequest request = RegisterRequest.builder()
                .email("otpfail@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .phoneNumber("+1234567890")
                .build();

        when(userRepository.existsByEmail("otpfail@hekma.com")).thenReturn(false);
        when(userRepository.existsByPhoneNumber("+1234567890")).thenReturn(false);
        when(firebaseService.getUserByEmail("otpfail@hekma.com")).thenReturn(Optional.empty());

        FirebaseUserDto fbDto = FirebaseUserDto.builder()
                .uid("fb-otpfail-id")
                .email("otpfail@hekma.com")
                .role(Role.PATIENT)
                .build();
        when(firebaseService.createUser(eq("otpfail@hekma.com"), eq("Password123!"), any(), eq(Role.PATIENT)))
                .thenReturn(fbDto);

        UserEntity savedEntity = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-otpfail-id")
                .email("otpfail@hekma.com")
                .role(Role.PATIENT)
                .phoneNumber("+1234567890")
                .status(UserStatus.PENDING_VERIFICATION)
                .build();
        when(userRepository.save(any(UserEntity.class))).thenReturn(savedEntity);

        when(otpService.sendOtp(any(SendOtpRequest.class), any()))
                .thenThrow(new RuntimeException("SMS gateway unavailable"));

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("SMS gateway unavailable");

        verify(userRepository).delete(savedEntity);
        verify(firebaseService).deleteUser("fb-otpfail-id");
    }

    @Test
    @DisplayName("inviteAdmin creates user with ADMIN role")
    void inviteAdmin_success() {
        InviteAdminRequest request = InviteAdminRequest.builder()
                .email("new.admin@hekma.com")
                .temporaryPassword("TempAdminPass123!")
                .displayName("New Administrator")
                .build();

        when(userRepository.existsByEmail("new.admin@hekma.com")).thenReturn(false);
        when(firebaseService.getUserByEmail("new.admin@hekma.com")).thenReturn(Optional.empty());

        FirebaseUserDto fbDto = FirebaseUserDto.builder()
                .uid("fb-admin-uid")
                .email("new.admin@hekma.com")
                .displayName("New Administrator")
                .role(Role.ADMIN)
                .build();
        when(firebaseService.createUser("new.admin@hekma.com", "TempAdminPass123!", "New Administrator", Role.ADMIN))
                .thenReturn(fbDto);

        UserEntity adminEntity = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-admin-uid")
                .email("new.admin@hekma.com")
                .role(Role.ADMIN)
                .displayName("New Administrator")
                .status(UserStatus.ACTIVE)
                .build();
        when(userRepository.save(any(UserEntity.class))).thenReturn(adminEntity);

        RegisterResponse response = authService.inviteAdmin(request, UUID.randomUUID());

        assertThat(response).isNotNull();
        assertThat(response.getRole()).isEqualTo(Role.ADMIN);
        assertThat(response.getEmail()).isEqualTo("new.admin@hekma.com");
    }

    @Test
    @DisplayName("initializeSystemAdmin creates System Admin with random password when none exists")
    void initializeSystemAdmin_createsWhenAbsent() {
        String email = "sysadmin@hekma.com";
        String name = "System Administrator";

        when(userRepository.existsByRole(Role.SYSTEM_ADMIN)).thenReturn(false);
        when(userRepository.existsByEmail(email)).thenReturn(false);
        when(firebaseService.getUserByEmail(email)).thenReturn(Optional.empty());

        FirebaseUserDto fbDto = FirebaseUserDto.builder()
                .uid("fb-sysadmin-uid")
                .email(email)
                .role(Role.SYSTEM_ADMIN)
                .build();
        when(firebaseService.createUser(eq(email), argThat(pass -> pass != null && pass.length() >= 8), eq(name), eq(Role.SYSTEM_ADMIN)))
                .thenReturn(fbDto);

        authService.initializeSystemAdmin(email, name);

        verify(userRepository).save(argThat(entity ->
                entity.getRole() == Role.SYSTEM_ADMIN &&
                        entity.getEmail().equals(email) &&
                        entity.getFirebaseUid().equals("fb-sysadmin-uid")
        ));
    }

    @Test
    @DisplayName("initializeSystemAdmin skips creation when System Admin already exists")
    void initializeSystemAdmin_skipsWhenPresent() {
        when(userRepository.existsByRole(Role.SYSTEM_ADMIN)).thenReturn(true);

        authService.initializeSystemAdmin("sysadmin@hekma.com", "System Administrator");

        verify(userRepository, never()).save(any());
        verify(firebaseService, never()).createUser(anyString(), anyString(), anyString(), any());
    }

    @Test
    @DisplayName("refreshToken with valid token and active user returns refreshed tokens and user details")
    void refreshToken_success() {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("valid-refresh-token")
                .build();

        FirebaseTokenRefreshResponse fbResponse = FirebaseTokenRefreshResponse.builder()
                .idToken("new-id-token-abc")
                .refreshToken("new-refresh-token-xyz")
                .tokenType("Bearer")
                .expiresIn(3600L)
                .firebaseUid(sampleEntity.getFirebaseUid())
                .build();

        when(firebaseService.refreshToken("valid-refresh-token")).thenReturn(fbResponse);
        when(userRepository.findByFirebaseUid(sampleEntity.getFirebaseUid())).thenReturn(Optional.of(sampleEntity));

        RefreshTokenResponse response = authService.refreshToken(request);

        assertThat(response).isNotNull();
        assertThat(response.getIdToken()).isEqualTo("new-id-token-abc");
        assertThat(response.getRefreshToken()).isEqualTo("new-refresh-token-xyz");
        assertThat(response.getTokenType()).isEqualTo("Bearer");
        assertThat(response.getExpiresIn()).isEqualTo(3600L);
        assertThat(response.getFirebaseUid()).isEqualTo(sampleEntity.getFirebaseUid());
        assertThat(response.getEmail()).isEqualTo(sampleEntity.getEmail());
        assertThat(response.getRole()).isEqualTo(sampleEntity.getRole());
        assertThat(response.getStatus()).isEqualTo(UserStatus.ACTIVE);
    }

    @Test
    @DisplayName("refreshToken when user is not found in database throws InvalidTokenException")
    void refreshToken_userNotFoundInDb_throwsInvalidTokenException() {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("token-for-deleted-user")
                .build();

        FirebaseTokenRefreshResponse fbResponse = FirebaseTokenRefreshResponse.builder()
                .idToken("new-id-token")
                .refreshToken("new-refresh-token")
                .firebaseUid("orphan-firebase-uid")
                .build();

        when(firebaseService.refreshToken("token-for-deleted-user")).thenReturn(fbResponse);
        when(userRepository.findByFirebaseUid("orphan-firebase-uid")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> authService.refreshToken(request))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessageContaining("No registered user found");
    }

    @Test
    @DisplayName("refreshToken for suspended user throws UserInactiveException")
    void refreshToken_suspendedUser_throwsUserInactiveException() {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("token-suspended-user")
                .build();

        UserEntity suspendedUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-suspended-uid")
                .email("suspended@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.SUSPENDED)
                .build();

        FirebaseTokenRefreshResponse fbResponse = FirebaseTokenRefreshResponse.builder()
                .idToken("new-id-token")
                .refreshToken("new-refresh-token")
                .firebaseUid("fb-suspended-uid")
                .build();

        when(firebaseService.refreshToken("token-suspended-user")).thenReturn(fbResponse);
        when(userRepository.findByFirebaseUid("fb-suspended-uid")).thenReturn(Optional.of(suspendedUser));

        assertThatThrownBy(() -> authService.refreshToken(request))
                .isInstanceOf(UserInactiveException.class)
                .hasMessageContaining("suspended");
    }

    @Test
    @DisplayName("refreshToken with blank token throws InvalidTokenException")
    void refreshToken_blankToken_throwsInvalidTokenException() {
        RefreshTokenRequest request = RefreshTokenRequest.builder()
                .refreshToken("   ")
                .build();

        assertThatThrownBy(() -> authService.refreshToken(request))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessageContaining("must not be blank");
    }

    @Test
    @DisplayName("Public registration with only email succeeds and selects EMAIL verification mode")
    void register_emailOnly_success() {
        UUID otpAttemptId = UUID.randomUUID();
        RegisterRequest request = RegisterRequest.builder()
                .email("emailonly@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .displayName("Email Only User")
                .verificationMode(VerificationMode.EMAIL)
                .build();

        when(userRepository.existsByEmail("emailonly@hekma.com")).thenReturn(false);
        when(firebaseService.getUserByEmail("emailonly@hekma.com")).thenReturn(Optional.empty());

        FirebaseUserDto fbDto = FirebaseUserDto.builder()
                .uid("fb-uid-emailonly")
                .email("emailonly@hekma.com")
                .displayName("Email Only User")
                .role(Role.PATIENT)
                .build();
        when(firebaseService.createUser("emailonly@hekma.com", "Password123!", "Email Only User", Role.PATIENT)).thenReturn(fbDto);

        UserEntity savedEntity = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-uid-emailonly")
                .email("emailonly@hekma.com")
                .role(Role.PATIENT)
                .displayName("Email Only User")
                .status(UserStatus.PENDING_VERIFICATION)
                .phoneVerified(false)
                .emailVerified(false)
                .verificationMode(VerificationMode.EMAIL)
                .createdAt(Instant.now())
                .build();
        when(userRepository.save(any(UserEntity.class))).thenReturn(savedEntity);

        SendOtpResponse otpResponse = SendOtpResponse.builder()
                .attemptId(otpAttemptId)
                .email("emailonly@hekma.com")
                .verificationMode(VerificationMode.EMAIL)
                .expiresInSeconds(300L)
                .message("OTP has been sent to your registered email address.")
                .build();
        when(otpService.sendOtp(any(SendOtpRequest.class), any())).thenReturn(otpResponse);

        RegisterResponse response = authService.register(request);

        assertThat(response).isNotNull();
        assertThat(response.getEmail()).isEqualTo("emailonly@hekma.com");
        assertThat(response.getPhoneNumber()).isNull();
        assertThat(response.getPhoneVerified()).isFalse();
        assertThat(response.getEmailVerified()).isFalse();
        assertThat(response.getVerificationMode()).isEqualTo(VerificationMode.EMAIL);
        assertThat(response.getOtpAttemptId()).isEqualTo(otpAttemptId);
        assertThat(response.getMessage()).contains("OTP has been sent to your email address");

        verify(otpService).sendOtp(argThat(r -> r.getVerificationMode() == VerificationMode.EMAIL && "emailonly@hekma.com".equals(r.getEmail())), any());
        verify(notificationServiceClient).sendWelcomeEmail(eq("emailonly@hekma.com"), eq("Email Only User"));
    }

    @Test
    @DisplayName("Public registration with only phone succeeds and selects PHONE verification mode")
    void register_phoneOnly_success() {
        UUID otpAttemptId = UUID.randomUUID();
        RegisterRequest request = RegisterRequest.builder()
                .phoneNumber("+1234567890")
                .password("Password123!")
                .role(Role.PATIENT)
                .displayName("Phone Only User")
                .verificationMode(VerificationMode.PHONE)
                .build();

        when(userRepository.existsByPhoneNumber("+1234567890")).thenReturn(false);

        FirebaseUserDto fbDto = FirebaseUserDto.builder()
                .uid("fb-uid-phoneonly")
                .displayName("Phone Only User")
                .role(Role.PATIENT)
                .build();
        when(firebaseService.createUser(argThat(e -> e != null && e.endsWith("@" + AuthEmails.SYNTHETIC_DOMAIN)),
                eq("Password123!"), eq("Phone Only User"), eq(Role.PATIENT))).thenReturn(fbDto);

        UserEntity savedEntity = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-uid-phoneonly")
                .phoneNumber("+1234567890")
                .role(Role.PATIENT)
                .displayName("Phone Only User")
                .status(UserStatus.PENDING_VERIFICATION)
                .phoneVerified(false)
                .emailVerified(false)
                .verificationMode(VerificationMode.PHONE)
                .createdAt(Instant.now())
                .build();
        when(userRepository.save(any(UserEntity.class))).thenReturn(savedEntity);

        SendOtpResponse otpResponse = SendOtpResponse.builder()
                .attemptId(otpAttemptId)
                .phoneNumber("+1234567890")
                .verificationMode(VerificationMode.PHONE)
                .expiresInSeconds(300L)
                .message("OTP generated (printed to console for dev testing).")
                .build();
        when(otpService.sendOtp(any(SendOtpRequest.class), any())).thenReturn(otpResponse);

        RegisterResponse response = authService.register(request);

        assertThat(response).isNotNull();
        assertThat(response.getPhoneNumber()).isEqualTo("+1234567890");
        assertThat(response.getEmail()).isNull();
        assertThat(response.getPhoneVerified()).isFalse();
        assertThat(response.getEmailVerified()).isFalse();
        assertThat(response.getVerificationMode()).isEqualTo(VerificationMode.PHONE);
        assertThat(response.getOtpAttemptId()).isEqualTo(otpAttemptId);
        assertThat(response.getMessage()).contains("phone verification");

        verify(otpService).sendOtp(argThat(r -> r.getVerificationMode() == VerificationMode.PHONE && "+1234567890".equals(r.getPhoneNumber())), any());
        verify(notificationServiceClient, never()).sendWelcomeEmail(any(), any());
        verify(notificationServiceClient).sendWelcomeInApp(eq(savedEntity.getId()), eq("Phone Only User"));
    }

    @Test
    @DisplayName("Public registration with neither email nor phone throws IllegalArgumentException")
    void register_neitherEmailNorPhone_throwsIllegalArgumentException() {
        RegisterRequest request = RegisterRequest.builder()
                .password("Password123!")
                .role(Role.PATIENT)
                .build();

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("At least one of email or phone number is required");
    }

    @Test
    @DisplayName("Public registration with verification mode PHONE but phone missing throws IllegalArgumentException")
    void register_phoneChannelWithoutPhone_throwsIllegalArgumentException() {
        RegisterRequest request = RegisterRequest.builder()
                .email("user@hekma.com")
                .password("Password123!")
                .role(Role.PATIENT)
                .verificationMode(VerificationMode.PHONE)
                .build();

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Phone number is required when verification mode is PHONE");
    }

    @Test
    @DisplayName("Public registration with verification mode EMAIL but email missing throws IllegalArgumentException")
    void register_emailChannelWithoutEmail_throwsIllegalArgumentException() {
        RegisterRequest request = RegisterRequest.builder()
                .phoneNumber("+1234567890")
                .password("Password123!")
                .role(Role.PATIENT)
                .verificationMode(VerificationMode.EMAIL)
                .build();

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Email is required when verification mode is EMAIL");
    }

    // ==========================================
    // Login Tests (including 2FA conditional logic)
    // ==========================================

    @Test
    @DisplayName("Login for PATIENT with 2FA disabled returns tokens directly")
    void login_patientWithTwoFactorDisabled_returnsTokensDirectly() {
        UUID userId = UUID.randomUUID();
        UserEntity patient = UserEntity.builder()
                .id(userId)
                .email("patient@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .twoFactorEnabled(false)
                .firebaseUid("fb-uid-patient")
                .displayName("John Patient")
                .build();

        when(userRepository.findByEmail("patient@hekma.com")).thenReturn(Optional.of(patient));
        when(firebaseService.signInWithPassword("patient@hekma.com", "Password123!")).thenReturn(
                FirebaseSignInResponse.builder()
                        .idToken("mock-id-token")
                        .refreshToken("mock-refresh-token")
                        .expiresIn(3600L)
                        .firebaseUid("fb-uid-patient")
                        .email("patient@hekma.com")
                        .build()
        );

        LoginRequest request = LoginRequest.builder()
                .email("patient@hekma.com")
                .password("Password123!")
                .build();

        LoginResponse response = authService.login(request);

        assertThat(response.isTwoFactorRequired()).isFalse();
        assertThat(response.getTwoFactorEnabled()).isFalse();
        assertThat(response.getIdToken()).isEqualTo("mock-id-token");
        assertThat(response.getRefreshToken()).isEqualTo("mock-refresh-token");
        assertThat(response.getUserId()).isEqualTo(userId);
        assertThat(response.getRole()).isEqualTo(Role.PATIENT);
        verify(otpService, never()).sendOtp(any(), any());
    }

    @Test
    @DisplayName("Login for PATIENT with 2FA enabled dispatches OTP and returns twoFactorRequired=true")
    void login_patientWithTwoFactorEnabled_dispatchesOtpAndReturnsTwoFactorRequired() {
        UUID userId = UUID.randomUUID();
        UUID otpAttemptId = UUID.randomUUID();
        UserEntity patient = UserEntity.builder()
                .id(userId)
                .email("patient@hekma.com")
                .phoneNumber("+1234567890")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .twoFactorEnabled(true)
                .verificationMode(VerificationMode.PHONE)
                .firebaseUid("fb-uid-patient")
                .displayName("John Patient")
                .build();

        when(userRepository.findByEmail("patient@hekma.com")).thenReturn(Optional.of(patient));
        when(firebaseService.signInWithPassword("patient@hekma.com", "Password123!")).thenReturn(
                FirebaseSignInResponse.builder()
                        .idToken("mock-id-token")
                        .refreshToken("mock-refresh-token")
                        .expiresIn(3600L)
                        .firebaseUid("fb-uid-patient")
                        .email("patient@hekma.com")
                        .build()
        );
        when(otpService.sendOtp(any(SendOtpRequest.class), any())).thenReturn(
                SendOtpResponse.builder()
                        .attemptId(otpAttemptId)
                        .expiresInSeconds(300L)
                        .message("OTP sent")
                        .build()
        );

        LoginRequest request = LoginRequest.builder()
                .email("patient@hekma.com")
                .password("Password123!")
                .build();

        LoginResponse response = authService.login(request, "127.0.0.1");

        assertThat(response.isTwoFactorRequired()).isTrue();
        assertThat(response.getTwoFactorEnabled()).isTrue();
        assertThat(response.getOtpAttemptId()).isEqualTo(otpAttemptId);
        assertThat(response.getOtpExpiresInSeconds()).isEqualTo(300L);
        assertThat(response.getIdToken()).isNull();
        assertThat(response.getRefreshToken()).isNull();
        assertThat(response.getMessage()).contains("Two-factor authentication required");

        verify(otpService).sendOtp(argThat(otpReq ->
                otpReq.getPurpose() == OtpPurpose.RE_AUTHENTICATION &&
                otpReq.getVerificationMode() == VerificationMode.PHONE
        ), eq("127.0.0.1"));
    }

    @Test
    @DisplayName("Login for non-patient roles (e.g. SPONSOR, ADMIN) returns tokens directly without 2FA")
    void login_sponsorRole_returnsTokensDirectlyWithout2fa() {
        UUID userId = UUID.randomUUID();
        UserEntity sponsor = UserEntity.builder()
                .id(userId)
                .email("sponsor@pharma.com")
                .role(Role.SPONSOR)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .twoFactorEnabled(true) // Even if true on record, non-patient roles bypass 2FA
                .firebaseUid("fb-uid-sponsor")
                .displayName("Sponsor Rep")
                .build();

        when(userRepository.findByEmail("sponsor@pharma.com")).thenReturn(Optional.of(sponsor));
        when(firebaseService.signInWithPassword("sponsor@pharma.com", "Password123!")).thenReturn(
                FirebaseSignInResponse.builder()
                        .idToken("mock-id-token-sponsor")
                        .refreshToken("mock-refresh-token-sponsor")
                        .expiresIn(3600L)
                        .firebaseUid("fb-uid-sponsor")
                        .email("sponsor@pharma.com")
                        .build()
        );

        LoginRequest request = LoginRequest.builder()
                .email("sponsor@pharma.com")
                .password("Password123!")
                .build();

        LoginResponse response = authService.login(request);

        assertThat(response.isTwoFactorRequired()).isFalse();
        assertThat(response.getIdToken()).isEqualTo("mock-id-token-sponsor");
        verify(otpService, never()).sendOtp(any(), any());
    }

    @Test
    @DisplayName("Login for inactive user throws UserInactiveException")
    void login_inactiveUser_throwsUserInactiveException() {
        UserEntity inactiveUser = UserEntity.builder()
                .email("inactive@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.INACTIVE)
                .isActive(false)
                .build();

        when(userRepository.findByEmail("inactive@hekma.com")).thenReturn(Optional.of(inactiveUser));

        LoginRequest request = LoginRequest.builder()
                .email("inactive@hekma.com")
                .password("Password123!")
                .build();

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(UserInactiveException.class)
                .hasMessageContaining("Authentication denied");
    }

    @Test
    @DisplayName("Login for non-existent user throws InvalidTokenException")
    void login_userNotFound_throwsInvalidTokenException() {
        when(userRepository.findByEmail("unknown@hekma.com")).thenReturn(Optional.empty());

        LoginRequest request = LoginRequest.builder()
                .email("unknown@hekma.com")
                .password("Password123!")
                .build();

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessageContaining("Invalid email/phone or password");
    }

    @Test
    @DisplayName("Login with blank password throws IllegalArgumentException")
    void login_blankPassword_throwsIllegalArgumentException() {
        LoginRequest request = LoginRequest.builder()
                .email("user@hekma.com")
                .password("   ")
                .build();

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Password must not be blank");
    }

    @Test
    @DisplayName("Login with missing email and phone throws IllegalArgumentException")
    void login_missingIdentifier_throwsIllegalArgumentException() {
        LoginRequest request = LoginRequest.builder()
                .password("Password123!")
                .build();

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Email, phone number, or identifier is required for login");
    }
    // ==========================================
    // Phase 1 hardening
    // ==========================================

    @ParameterizedTest
    @EnumSource(value = Role.class, names = {"SPONSOR", "SITE", "ADMIN", "SYSTEM_ADMIN"})
    @DisplayName("Public registration rejects every role except PATIENT")
    void register_nonPatientRole_throwsInvalidRole(Role role) {
        RegisterRequest request = RegisterRequest.builder()
                .email("staff@hekma.com")
                .password("Password123!")
                .role(role)
                .phoneNumber("+1234567890")
                .build();

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(InvalidRoleException.class)
                .hasMessageContaining("Only PATIENT");
        verifyNoInteractions(firebaseService);
    }

    @Test
    @DisplayName("Login without a Firebase login email fails with a generic credentials error")
    void login_userWithoutAuthEmail_throwsInvalidCredentials() {
        UserEntity phoneOnly = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-phone")
                .phoneNumber("+1999000111")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .build();
        when(otpService.findUserByPhone("+1999000111")).thenReturn(Optional.of(phoneOnly));

        LoginRequest request = LoginRequest.builder()
                .phoneNumber("+1999000111")
                .password("whatever")
                .build();

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessageContaining("Invalid email/phone or password");
        verify(firebaseService, never()).createCustomToken(anyString());
        verify(firebaseService, never()).signInWithPassword(any(), any());
    }

    @Test
    @DisplayName("Login validates the password through Firebase using the auth email")
    void login_phoneUserWithAuthEmail_validatesPasswordWithFirebase() {
        UserEntity phoneUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-phone")
                .phoneNumber("+1999000222")
                .authEmail("phone-x@" + AuthEmails.SYNTHETIC_DOMAIN)
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .build();
        when(otpService.findUserByPhone("+1999000222")).thenReturn(Optional.of(phoneUser));
        when(firebaseService.signInWithPassword("phone-x@" + AuthEmails.SYNTHETIC_DOMAIN, "wrong"))
                .thenThrow(new InvalidTokenException("Invalid email or password."));

        LoginRequest request = LoginRequest.builder()
                .phoneNumber("+1999000222")
                .password("wrong")
                .build();

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidTokenException.class);
    }

    @Test
    @DisplayName("Password reset verifies the OTP before updating the password and revokes sessions")
    void resetPassword_verifiesOtpThenUpdatesPassword() {
        UserEntity user = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-reset")
                .email("reset@hekma.com")
                .authEmail("reset@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .build();
        when(userRepository.findByEmail("reset@hekma.com")).thenReturn(Optional.of(user));

        ResetPasswordRequest request = new ResetPasswordRequest();
        request.setIdentifier("reset@hekma.com");
        request.setOtpCode("123456");
        request.setNewPassword("NewPassword123!");

        authService.resetPassword(request, "127.0.0.1");

        InOrder order = inOrder(otpService, firebaseService);
        order.verify(otpService).verifyPasswordResetOtp(user, "123456", "127.0.0.1");
        order.verify(firebaseService).updatePassword("fb-reset", "NewPassword123!");
        order.verify(firebaseService).revokeRefreshTokens("fb-reset");
    }

    @Test
    @DisplayName("Password reset with an invalid OTP does not change the password")
    void resetPassword_invalidOtp_doesNotUpdatePassword() {
        UserEntity user = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-reset")
                .email("reset@hekma.com")
                .role(Role.SYSTEM_ADMIN)
                .status(UserStatus.ACTIVE)
                .build();
        when(userRepository.findByEmail("reset@hekma.com")).thenReturn(Optional.of(user));
        doThrow(new InvalidOtpException("Invalid OTP code. 4 attempts remaining."))
                .when(otpService).verifyPasswordResetOtp(eq(user), eq("000000"), any());

        ResetPasswordRequest request = new ResetPasswordRequest();
        request.setIdentifier("reset@hekma.com");
        request.setOtpCode("000000");
        request.setNewPassword("Attacker123!");

        assertThatThrownBy(() -> authService.resetPassword(request, "127.0.0.1"))
                .isInstanceOf(InvalidOtpException.class);
        verify(firebaseService, never()).updatePassword(any(), any());
    }

    @Test
    @DisplayName("Password reset for a phone-only account assigns a synthetic Firebase login email")
    void resetPassword_phoneOnlyAccount_assignsSyntheticAuthEmail() {
        UserEntity user = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-legacy-phone")
                .phoneNumber("+1999000333")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .build();
        when(userRepository.findByPhoneNumber("+1999000333")).thenReturn(Optional.of(user));

        ResetPasswordRequest request = new ResetPasswordRequest();
        request.setIdentifier("+1999000333");
        request.setOtpCode("123456");
        request.setNewPassword("NewPassword123!");

        authService.resetPassword(request, null);

        assertThat(user.getAuthEmail()).endsWith("@" + AuthEmails.SYNTHETIC_DOMAIN);
        verify(firebaseService).updateAuthEmail("fb-legacy-phone", user.getAuthEmail());
        verify(firebaseService).updatePassword("fb-legacy-phone", "NewPassword123!");
    }

    @Test
    @DisplayName("Forgot password returns the same message for known and unknown identifiers")
    void forgotPassword_unknownIdentifier_returnsUniformMessage() {
        when(userRepository.findByEmail("nobody@hekma.com")).thenReturn(Optional.empty());
        UserEntity known = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("known@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .build();
        when(userRepository.findByEmail("known@hekma.com")).thenReturn(Optional.of(known));

        ForgotPasswordRequest unknownRequest = new ForgotPasswordRequest();
        unknownRequest.setIdentifier("nobody@hekma.com");
        ForgotPasswordRequest knownRequest = new ForgotPasswordRequest();
        knownRequest.setIdentifier("known@hekma.com");

        assertThat(authService.forgotPassword(unknownRequest, null))
                .isEqualTo(authService.forgotPassword(knownRequest, null));
    }
    // ==========================================
    // changePassword
    // ==========================================

    private UserEntity passwordUser() {
        return UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-change")
                .email("change@hekma.com")
                .authEmail("change@hekma.com")
                .role(Role.SITE)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .build();
    }

    @Test
    @DisplayName("changePassword validates the current password, stores the new one, revokes sessions and returns new tokens")
    void changePassword_success() {
        UserEntity user = passwordUser();
        when(userRepository.findById(user.getId())).thenReturn(Optional.of(user));
        when(firebaseService.signInWithPassword("change@hekma.com", "OldPassword123!"))
                .thenReturn(FirebaseSignInResponse.builder().idToken("old").build());
        when(firebaseService.signInWithPassword("change@hekma.com", "NewPassword123!"))
                .thenReturn(FirebaseSignInResponse.builder().idToken("new-id").refreshToken("new-refresh").expiresIn(3600L).build());

        ChangePasswordResponse response = authService.changePassword(user.getId(),
                ChangePasswordRequest.builder().currentPassword("OldPassword123!").newPassword("NewPassword123!").build());

        assertThat(response.getIdToken()).isEqualTo("new-id");
        assertThat(response.getRefreshToken()).isEqualTo("new-refresh");
        InOrder order = inOrder(firebaseService);
        order.verify(firebaseService).signInWithPassword("change@hekma.com", "OldPassword123!");
        order.verify(firebaseService).updatePassword("fb-change", "NewPassword123!");
        order.verify(firebaseService).revokeRefreshTokens("fb-change");
        order.verify(firebaseService).signInWithPassword("change@hekma.com", "NewPassword123!");
    }

    @Test
    @DisplayName("changePassword with a wrong current password does not change anything")
    void changePassword_wrongCurrentPassword_throws() {
        UserEntity user = passwordUser();
        when(userRepository.findById(user.getId())).thenReturn(Optional.of(user));
        when(firebaseService.signInWithPassword("change@hekma.com", "WrongPassword1!"))
                .thenThrow(new InvalidTokenException("Invalid email or password."));

        assertThatThrownBy(() -> authService.changePassword(user.getId(),
                ChangePasswordRequest.builder().currentPassword("WrongPassword1!").newPassword("NewPassword123!").build()))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessageContaining("Current password is incorrect");
        verify(firebaseService, never()).updatePassword(any(), any());
        verify(firebaseService, never()).revokeRefreshTokens(any());
    }

    @Test
    @DisplayName("changePassword rejects a new password equal to the current one")
    void changePassword_samePassword_throws() {
        UserEntity user = passwordUser();
        when(userRepository.findById(user.getId())).thenReturn(Optional.of(user));

        assertThatThrownBy(() -> authService.changePassword(user.getId(),
                ChangePasswordRequest.builder().currentPassword("SamePassword123!").newPassword("SamePassword123!").build()))
                .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(firebaseService);
    }
}
