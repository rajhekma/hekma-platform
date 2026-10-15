package com.hekma.identity.service;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.OtpAuditEventType;
import com.hekma.identity.domain.otp.OtpAuditLogEntity;
import com.hekma.identity.domain.otp.VerificationMode;
import com.hekma.identity.domain.otp.OtpLockoutEntity;
import com.hekma.identity.domain.otp.OtpPurpose;
import com.hekma.identity.domain.otp.OtpRequestEntity;
import com.hekma.identity.domain.otp.OtpStatus;
import com.hekma.identity.dto.otp.ResendOtpRequest;
import com.hekma.identity.dto.otp.ResendOtpResponse;
import com.hekma.identity.dto.otp.SendOtpRequest;
import com.hekma.identity.dto.otp.SendOtpResponse;
import com.hekma.identity.dto.otp.VerifyOtpRequest;
import com.hekma.identity.dto.otp.VerifyOtpResponse;
import com.hekma.identity.exception.InvalidOtpException;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.exception.OtpExpiredException;
import com.hekma.identity.exception.OtpLockoutException;
import com.hekma.identity.exception.OtpResendLimitException;
import com.hekma.identity.exception.OtpVerificationLimitException;
import com.hekma.identity.exception.UserInactiveException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseSignInResponse;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.repository.OtpAuditLogRepository;
import com.hekma.identity.repository.OtpLockoutRepository;
import com.hekma.identity.repository.OtpRequestRepository;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Map;
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
class OtpServiceTest {

    @Mock
    private OtpRequestRepository otpRequestRepository;

    @Mock
    private OtpLockoutRepository otpLockoutRepository;

    @Mock
    private OtpAuditLogRepository otpAuditLogRepository;

    @Mock
    private PatientDetailRepository patientDetailRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private PasswordEncoder passwordEncoder;

    @Mock
    private FirebaseService firebaseService;

    @Mock
    private NotificationServiceClient notificationServiceClient;

    @InjectMocks
    private OtpService otpService;

    private final String phone = "+1234567890";
    private final UUID attemptId = UUID.randomUUID();
    private UserEntity sampleUser;
    private PatientDetailEntity samplePatient;

    @BeforeEach
    void setUp() {
        sampleUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-uid-123")
                .email("patient@example.com")
                .role(Role.PATIENT)
                .displayName("John Doe")
                .status(UserStatus.ACTIVE)
                .build();

        samplePatient = PatientDetailEntity.builder()
                .id(UUID.randomUUID())
                .user(sampleUser)
                .firstName("John")
                .lastName("Doe")
                .phoneNumber(phone)
                .build();
    }

    // ==========================================
    // Send OTP Tests
    // ==========================================

    @Test
    @DisplayName("sendOtp: successful dispatch for login purpose")
    void sendOtp_Success_Login() {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.LOGIN)
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(0L);
        when(patientDetailRepository.findByPhoneNumber(phone)).thenReturn(Optional.of(samplePatient));
        when(passwordEncoder.encode(anyString())).thenReturn("hashed-otp-123");
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(invocation -> {
            OtpRequestEntity entity = invocation.getArgument(0);
            entity.setId(attemptId);
            return entity;
        });

        SendOtpResponse response = otpService.sendOtp(request, "127.0.0.1");

        assertThat(response).isNotNull();
        assertThat(response.getAttemptId()).isEqualTo(attemptId);
        assertThat(response.getPhoneNumber()).isEqualTo(phone);
        assertThat(response.getMessage()).contains("OTP generated");

        verify(notificationServiceClient, never()).sendOtpSms(any(), any(), any());
        verify(otpAuditLogRepository).save(argThat(log ->
                log.getEventType() == OtpAuditEventType.GENERATION && log.getAttemptId().equals(attemptId)));
    }

    @Test
    @DisplayName("sendOtp: registration purpose allows non-registered phone number")
    void sendOtp_Success_Registration_NonRegisteredPhone() {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.REGISTRATION)
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(0L);
        when(passwordEncoder.encode(anyString())).thenReturn("hashed-otp-123");
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(invocation -> {
            OtpRequestEntity entity = invocation.getArgument(0);
            entity.setId(attemptId);
            return entity;
        });

        SendOtpResponse response = otpService.sendOtp(request, "127.0.0.1");

        assertThat(response).isNotNull();
        assertThat(response.getAttemptId()).isEqualTo(attemptId);
        verify(patientDetailRepository, never()).findByPhoneNumber(anyString());
    }

    @Test
    @DisplayName("sendOtp: login fails if patient is not registered")
    void sendOtp_Login_PatientNotFound_ThrowsException() {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.LOGIN)
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(1L);
        when(patientDetailRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> otpService.sendOtp(request, "127.0.0.1"))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessageContaining("No registered account found");

        verify(otpRequestRepository, never()).save(any());
        verify(notificationServiceClient, never()).sendOtpSms(any(), any(), any());
    }

    @Test
    @DisplayName("sendOtp: login fails if patient account is inactive")
    void sendOtp_Login_PatientInactive_ThrowsException() {
        sampleUser.setStatus(UserStatus.SUSPENDED);
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.LOGIN)
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(0L);
        when(patientDetailRepository.findByPhoneNumber(phone)).thenReturn(Optional.of(samplePatient));

        assertThatThrownBy(() -> otpService.sendOtp(request, "127.0.0.1"))
                .isInstanceOf(UserInactiveException.class)
                .hasMessageContaining("Account is suspended");
    }

    @Test
    @DisplayName("sendOtp: throws OtpLockoutException if user is actively locked out")
    void sendOtp_ActiveLockout_ThrowsException() {
        SendOtpRequest request = SendOtpRequest.builder().phoneNumber(phone).build();
        Instant futureLockout = Instant.now().plus(20, ChronoUnit.MINUTES);
        OtpLockoutEntity lockout = OtpLockoutEntity.builder()
                .phoneNumber(phone)
                .lockedUntil(futureLockout)
                .lockReason("Hourly OTP request limit exceeded")
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.of(lockout));

        assertThatThrownBy(() -> otpService.sendOtp(request, "127.0.0.1"))
                .isInstanceOf(OtpLockoutException.class)
                .hasMessageContaining("Your OTP limit is reached, please come back at");

        verify(otpRequestRepository, never()).save(any());
    }

    @Test
    @DisplayName("sendOtp: clears expired lockout and proceeds")
    void sendOtp_ExpiredLockout_ClearsAndProceeds() {
        SendOtpRequest request = SendOtpRequest.builder()
                .phoneNumber(phone)
                .purpose(OtpPurpose.REGISTRATION)
                .build();

        Instant pastLockout = Instant.now().minus(5, ChronoUnit.MINUTES);
        OtpLockoutEntity lockout = OtpLockoutEntity.builder()
                .phoneNumber(phone)
                .lockedUntil(pastLockout)
                .lockReason("Old lockout")
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.of(lockout));
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(2L);
        when(passwordEncoder.encode(anyString())).thenReturn("hashed-otp");
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(invocation -> {
            OtpRequestEntity entity = invocation.getArgument(0);
            entity.setId(attemptId);
            return entity;
        });

        SendOtpResponse response = otpService.sendOtp(request, "127.0.0.1");

        verify(otpLockoutRepository).delete(lockout);
        assertThat(response).isNotNull();
    }

    @Test
    @DisplayName("sendOtp: triggers 30-min lockout when hourly limit (5) is reached")
    void sendOtp_HourlyLimitReached_TriggersLockout() {
        SendOtpRequest request = SendOtpRequest.builder().phoneNumber(phone).build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(5L);

        assertThatThrownBy(() -> otpService.sendOtp(request, "127.0.0.1"))
                .isInstanceOf(OtpLockoutException.class)
                .hasMessageContaining("Your OTP limit is reached, please come back at");

        verify(otpLockoutRepository).save(argThat(lock ->
                lock.getPhoneNumber().equals(phone) && lock.getLockedUntil().isAfter(Instant.now().plus(28, ChronoUnit.MINUTES))));
        verify(otpAuditLogRepository).save(argThat(log -> log.getEventType() == OtpAuditEventType.LOCKOUT));
    }

    // ==========================================
    // Resend OTP Tests
    // ==========================================

    @Test
    @DisplayName("resendOtp: successful resend increments count and resets 5-min validity")
    void resendOtp_Success() {
        ResendOtpRequest request = ResendOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .build();

        OtpRequestEntity existingAttempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .hashedOtp("old-hashed-otp")
                .resendCount(1)
                .verificationAttempts(2)
                .status(OtpStatus.PENDING)
                .expiresAt(Instant.now().plus(1, ChronoUnit.MINUTES))
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(2L);
        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(existingAttempt));
        when(passwordEncoder.encode(anyString())).thenReturn("new-hashed-otp");
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(i -> i.getArgument(0));

        ResendOtpResponse response = otpService.resendOtp(request, "127.0.0.1");

        assertThat(response).isNotNull();
        assertThat(response.getAttemptId()).isEqualTo(attemptId);
        assertThat(response.getResendCount()).isEqualTo(2);
        assertThat(response.getResendsRemaining()).isEqualTo(1); // 3 - 2 = 1
        assertThat(response.getExpiresInSeconds()).isEqualTo(300);

        assertThat(existingAttempt.getVerificationAttempts()).isEqualTo(0);
        assertThat(existingAttempt.getResendCount()).isEqualTo(2);
        verify(notificationServiceClient, never()).sendOtpSms(any(), any(), any());
        verify(otpAuditLogRepository).save(argThat(log -> log.getEventType() == OtpAuditEventType.RESEND));
    }

    @Test
    @DisplayName("resendOtp: fails when max resends (3) reached for attempt")
    void resendOtp_MaxResendsReached_ThrowsException() {
        ResendOtpRequest request = ResendOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .build();

        OtpRequestEntity existingAttempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .resendCount(3)
                .status(OtpStatus.PENDING)
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(3L);
        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(existingAttempt));

        assertThatThrownBy(() -> otpService.resendOtp(request, "127.0.0.1"))
                .isInstanceOf(OtpResendLimitException.class)
                .hasMessageContaining("Maximum OTP resend limit reached for this authentication attempt");

        verify(notificationServiceClient, never()).sendOtpSms(any(), any(), any());
    }

    @Test
    @DisplayName("resendOtp: fails if attempt already verified")
    void resendOtp_AlreadyVerified_ThrowsException() {
        ResendOtpRequest request = ResendOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .build();

        OtpRequestEntity existingAttempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .status(OtpStatus.VERIFIED)
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(1L);
        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(existingAttempt));

        assertThatThrownBy(() -> otpService.resendOtp(request, "127.0.0.1"))
                .isInstanceOf(InvalidOtpException.class)
                .hasMessageContaining("already been verified");
    }

    @Test
    @DisplayName("resendOtp: fails if attempt was invalidated")
    void resendOtp_InvalidatedAttempt_ThrowsException() {
        ResendOtpRequest request = ResendOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .build();

        OtpRequestEntity existingAttempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .status(OtpStatus.INVALIDATED)
                .build();

        when(otpLockoutRepository.findByPhoneNumber(phone)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindow(eq(phone), any(Instant.class))).thenReturn(1L);
        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(existingAttempt));

        assertThatThrownBy(() -> otpService.resendOtp(request, "127.0.0.1"))
                .isInstanceOf(OtpVerificationLimitException.class)
                .hasMessageContaining("invalidated");
    }

    // ==========================================
    // Verify OTP Tests
    // ==========================================

    @Test
    @DisplayName("verifyOtp: successful verification for registered patient returns custom token")
    void verifyOtp_Success_RegisteredPatient() {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123456")
                .build();

        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .hashedOtp("bcrypt-hashed-123456")
                .status(OtpStatus.PENDING)
                .verificationAttempts(0)
                .expiresAt(Instant.now().plus(4, ChronoUnit.MINUTES))
                .build();

        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(attempt));
        when(passwordEncoder.matches("123456", "bcrypt-hashed-123456")).thenReturn(true);
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(i -> i.getArgument(0));
        when(patientDetailRepository.findByPhoneNumber(phone)).thenReturn(Optional.of(samplePatient));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(i -> i.getArgument(0));
        when(firebaseService.createCustomToken(eq("fb-uid-123"), any())).thenReturn("mock-custom-token-fb-uid-123");
        when(firebaseService.signInWithCustomToken("mock-custom-token-fb-uid-123")).thenReturn(FirebaseSignInResponse.builder()
                .idToken("id-token-from-mock-custom-token-fb-uid-123").refreshToken("refresh-token").expiresIn(3600L).build());

        VerifyOtpResponse response = otpService.verifyOtp(request, "127.0.0.1");

        assertThat(response).isNotNull();
        assertThat(response.isVerified()).isTrue();
        assertThat(response.getAttemptId()).isEqualTo(attemptId);
        assertThat(response.getPhoneNumber()).isEqualTo(phone);
        assertThat(response.getPhoneVerified()).isTrue();
        assertThat(response.getVerificationMode()).isEqualTo(VerificationMode.PHONE);
        assertThat(response.getFirebaseCustomToken()).isEqualTo("mock-custom-token-fb-uid-123");
        assertThat(response.getEmail()).isEqualTo("patient@example.com");
        assertThat(response.getRole()).isEqualTo(Role.PATIENT);
        assertThat(response.getDisplayName()).isEqualTo("John Doe");

        assertThat(attempt.getStatus()).isEqualTo(OtpStatus.VERIFIED);
        assertThat(attempt.getVerifiedAt()).isNotNull();
        verify(otpAuditLogRepository).save(argThat(log -> log.getEventType() == OtpAuditEventType.VERIFICATION_SUCCESS));
    }

    @Test
    @DisplayName("verifyOtp: activates PENDING_VERIFICATION user upon successful verification")
    void verifyOtp_activatesPendingVerificationUser_success() {
        com.hekma.identity.domain.TenantEntity tenant = com.hekma.identity.domain.TenantEntity.builder()
                .id(UUID.randomUUID())
                .name("Test Tenant")
                .slug("test-tenant")
                .build();

        UserEntity pendingUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-pending-123")
                .email("pending@hekma.com")
                .role(Role.SPONSOR)
                .displayName("Dr. Sponsor")
                .phoneNumber(phone)
                .status(UserStatus.PENDING_VERIFICATION)
                .isActive(false)
                .tenant(tenant)
                .build();

        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123456")
                .build();

        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .hashedOtp("bcrypt-hashed-123456")
                .status(OtpStatus.PENDING)
                .verificationAttempts(0)
                .expiresAt(Instant.now().plus(4, ChronoUnit.MINUTES))
                .build();

        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(attempt));
        when(passwordEncoder.matches("123456", "bcrypt-hashed-123456")).thenReturn(true);
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(i -> i.getArgument(0));
        when(userRepository.findByPhoneNumber(phone)).thenReturn(Optional.of(pendingUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(i -> i.getArgument(0));
        when(firebaseService.createCustomToken(eq("fb-pending-123"), any())).thenReturn("mock-custom-token-fb-pending-123");
        when(firebaseService.signInWithCustomToken("mock-custom-token-fb-pending-123")).thenReturn(FirebaseSignInResponse.builder()
                .idToken("id-token-from-mock-custom-token-fb-pending-123").refreshToken("refresh-token").expiresIn(3600L).build());

        VerifyOtpResponse response = otpService.verifyOtp(request, "127.0.0.1");

        assertThat(response).isNotNull();
        assertThat(response.isVerified()).isTrue();
        assertThat(response.getRole()).isEqualTo(Role.SPONSOR);
        assertThat(response.getMessage()).contains("Account activated");
        assertThat(response.getTenantId()).isEqualTo(tenant.getId());
        assertThat(response.getTenantSlug()).isEqualTo("test-tenant");
        assertThat(pendingUser.getStatus()).isEqualTo(UserStatus.ACTIVE);
        assertThat(pendingUser.getIsActive()).isTrue();
        verify(userRepository).save(pendingUser);
        verify(firebaseService).createCustomToken(eq("fb-pending-123"), argThat(claims ->
                "SPONSOR".equals(claims.get("role")) &&
                tenant.getId().toString().equals(claims.get("tenantId")) &&
                !claims.containsKey("tenant_id")
        ));
    }

    @Test
    @DisplayName("verifyOtp: fails when OTP is expired (5-minute window elapsed)")
    void verifyOtp_ExpiredOtp_ThrowsException() {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123456")
                .build();

        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .hashedOtp("bcrypt-hashed-123456")
                .status(OtpStatus.PENDING)
                .verificationAttempts(0)
                .expiresAt(Instant.now().minus(1, ChronoUnit.SECONDS))
                .build();

        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(attempt));

        assertThatThrownBy(() -> otpService.verifyOtp(request, "127.0.0.1"))
                .isInstanceOf(OtpExpiredException.class)
                .hasMessageContaining("OTP has expired. Please request a new OTP.");

        assertThat(attempt.getStatus()).isEqualTo(OtpStatus.EXPIRED);
        verify(otpRequestRepository).save(attempt);
        verify(otpAuditLogRepository).save(argThat(log -> log.getEventType() == OtpAuditEventType.EXPIRATION));
    }

    @Test
    @DisplayName("verifyOtp: incorrect code increments attempts and shows remaining")
    void verifyOtp_IncorrectCode_IncrementsAttempts() {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("000000")
                .build();

        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .hashedOtp("bcrypt-hashed-123456")
                .status(OtpStatus.PENDING)
                .verificationAttempts(1)
                .expiresAt(Instant.now().plus(3, ChronoUnit.MINUTES))
                .build();

        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(attempt));
        when(passwordEncoder.matches("000000", "bcrypt-hashed-123456")).thenReturn(false);

        assertThatThrownBy(() -> otpService.verifyOtp(request, "127.0.0.1"))
                .isInstanceOf(InvalidOtpException.class)
                .hasMessageContaining("Invalid OTP code. 3 attempts remaining.");

        assertThat(attempt.getVerificationAttempts()).isEqualTo(2);
        verify(otpRequestRepository).save(attempt);
        verify(otpAuditLogRepository).save(argThat(log -> log.getEventType() == OtpAuditEventType.VERIFICATION_FAILURE));
    }

    @Test
    @DisplayName("verifyOtp: 5th incorrect attempt invalidates OTP")
    void verifyOtp_FifthIncorrectAttempt_InvalidatesOtp() {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("000000")
                .build();

        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .hashedOtp("bcrypt-hashed-123456")
                .status(OtpStatus.PENDING)
                .verificationAttempts(4)
                .expiresAt(Instant.now().plus(3, ChronoUnit.MINUTES))
                .build();

        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(attempt));
        when(passwordEncoder.matches("000000", "bcrypt-hashed-123456")).thenReturn(false);

        assertThatThrownBy(() -> otpService.verifyOtp(request, "127.0.0.1"))
                .isInstanceOf(OtpVerificationLimitException.class)
                .hasMessageContaining("Maximum verification attempts exceeded. This OTP is now invalid.");

        assertThat(attempt.getVerificationAttempts()).isEqualTo(5);
        assertThat(attempt.getStatus()).isEqualTo(OtpStatus.INVALIDATED);
        verify(otpRequestRepository).save(attempt);
        verify(otpAuditLogRepository).save(argThat(log -> log.getEventType() == OtpAuditEventType.VERIFICATION_FAILURE));
    }

    @Test
    @DisplayName("verifyOtp: attempt already verified throws exception")
    void verifyOtp_AlreadyVerified_ThrowsException() {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123456")
                .build();

        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(attemptId)
                .phoneNumber(phone)
                .status(OtpStatus.VERIFIED)
                .build();

        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.of(attempt));

        assertThatThrownBy(() -> otpService.verifyOtp(request, "127.0.0.1"))
                .isInstanceOf(InvalidOtpException.class)
                .hasMessageContaining("already been verified");
    }

    @Test
    @DisplayName("verifyOtp: attempt not found throws InvalidTokenException")
    void verifyOtp_AttemptNotFound_ThrowsException() {
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .phoneNumber(phone)
                .otpCode("123456")
                .build();

        when(otpRequestRepository.findByIdAndPhoneNumber(attemptId, phone)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> otpService.verifyOtp(request, "127.0.0.1"))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessageContaining("Authentication attempt not found");
    }

    @Test
    @DisplayName("sendOtp: successful email OTP dispatch calls NotificationServiceClient.sendOtpEmail")
    void sendOtp_Success_Email() {
        String email = "patient@example.com";
        SendOtpRequest request = SendOtpRequest.builder()
                .email(email)
                .verificationMode(VerificationMode.EMAIL)
                .purpose(OtpPurpose.REGISTRATION)
                .build();

        when(otpLockoutRepository.findByEmail(email)).thenReturn(Optional.empty());
        when(otpRequestRepository.countTotalOtpRequestsInWindowByEmail(eq(email), any(Instant.class))).thenReturn(0L);
        when(passwordEncoder.encode(anyString())).thenReturn("hashed-otp-email");
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(invocation -> {
            OtpRequestEntity entity = invocation.getArgument(0);
            entity.setId(attemptId);
            return entity;
        });

        SendOtpResponse response = otpService.sendOtp(request, "127.0.0.1");

        assertThat(response).isNotNull();
        assertThat(response.getAttemptId()).isEqualTo(attemptId);
        assertThat(response.getEmail()).isEqualTo(email);
        assertThat(response.getVerificationMode()).isEqualTo(VerificationMode.EMAIL);
        assertThat(response.getMessage()).contains("OTP has been sent to your registered email");

        verify(notificationServiceClient).sendOtpEmail(eq(email), anyString(), eq(attemptId));
        verify(notificationServiceClient, never()).sendOtpSms(any(), any(), any());
    }

    @Test
    @DisplayName("verifyOtp: successful verification for email-based attempt")
    void verifyOtp_Success_Email() {
        String email = "patient@example.com";
        VerifyOtpRequest request = VerifyOtpRequest.builder()
                .attemptId(attemptId)
                .email(email)
                .otpCode("123456")
                .build();

        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(attemptId)
                .email(email)
                .verificationMode(VerificationMode.EMAIL)
                .hashedOtp("hashed-123456")
                .status(OtpStatus.PENDING)
                .verificationAttempts(0)
                .expiresAt(Instant.now().plus(5, ChronoUnit.MINUTES))
                .build();

        when(otpRequestRepository.findByIdAndEmail(attemptId, email)).thenReturn(Optional.of(attempt));
        when(passwordEncoder.matches("123456", "hashed-123456")).thenReturn(true);
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(i -> i.getArgument(0));
        when(userRepository.findByEmail(email)).thenReturn(Optional.of(sampleUser));
        when(userRepository.save(any(UserEntity.class))).thenAnswer(i -> i.getArgument(0));
        when(firebaseService.createCustomToken(eq("fb-uid-123"), any())).thenReturn("firebase-custom-jwt-token");
        when(firebaseService.signInWithCustomToken("firebase-custom-jwt-token")).thenReturn(FirebaseSignInResponse.builder()
                .idToken("id-token-from-firebase-custom-jwt-token").refreshToken("refresh-token").expiresIn(3600L).build());

        VerifyOtpResponse response = otpService.verifyOtp(request, "127.0.0.1");

        assertThat(response).isNotNull();
        assertThat(response.isVerified()).isTrue();
        assertThat(response.getEmail()).isEqualTo(email);
        assertThat(response.getEmailVerified()).isTrue();
        assertThat(response.getVerificationMode()).isEqualTo(VerificationMode.EMAIL);
        assertThat(response.getFirebaseCustomToken()).isEqualTo("firebase-custom-jwt-token");
        assertThat(response.getIdToken()).isEqualTo("id-token-from-firebase-custom-jwt-token");
        assertThat(response.getRefreshToken()).isEqualTo("refresh-token");
    }

    // ==========================================
    // verifyPasswordResetOtp
    // ==========================================

    @Test
    @DisplayName("verifyPasswordResetOtp accepts the latest pending PASSWORD_RESET code and marks it verified")
    void verifyPasswordResetOtp_validCode_marksVerified() {
        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(UUID.randomUUID())
                .email("patient@example.com")
                .verificationMode(VerificationMode.EMAIL)
                .hashedOtp("hashed-654321")
                .purpose(OtpPurpose.PASSWORD_RESET)
                .status(OtpStatus.PENDING)
                .verificationAttempts(0)
                .expiresAt(Instant.now().plus(5, ChronoUnit.MINUTES))
                .build();
        when(otpRequestRepository.findTopByEmailAndStatusOrderByCreatedAtDesc("patient@example.com", OtpStatus.PENDING))
                .thenReturn(Optional.of(attempt));
        when(passwordEncoder.matches("654321", "hashed-654321")).thenReturn(true);
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(i -> i.getArgument(0));

        otpService.verifyPasswordResetOtp(sampleUser, "654321", "127.0.0.1");

        assertThat(attempt.getStatus()).isEqualTo(OtpStatus.VERIFIED);
    }

    @Test
    @DisplayName("verifyPasswordResetOtp rejects a wrong code and counts the attempt")
    void verifyPasswordResetOtp_wrongCode_throwsInvalidOtp() {
        OtpRequestEntity attempt = OtpRequestEntity.builder()
                .id(UUID.randomUUID())
                .email("patient@example.com")
                .verificationMode(VerificationMode.EMAIL)
                .hashedOtp("hashed-654321")
                .purpose(OtpPurpose.PASSWORD_RESET)
                .status(OtpStatus.PENDING)
                .verificationAttempts(0)
                .expiresAt(Instant.now().plus(5, ChronoUnit.MINUTES))
                .build();
        when(otpRequestRepository.findTopByEmailAndStatusOrderByCreatedAtDesc("patient@example.com", OtpStatus.PENDING))
                .thenReturn(Optional.of(attempt));
        when(passwordEncoder.matches("000000", "hashed-654321")).thenReturn(false);
        when(otpRequestRepository.save(any(OtpRequestEntity.class))).thenAnswer(i -> i.getArgument(0));

        assertThatThrownBy(() -> otpService.verifyPasswordResetOtp(sampleUser, "000000", "127.0.0.1"))
                .isInstanceOf(InvalidOtpException.class);
        assertThat(attempt.getVerificationAttempts()).isEqualTo(1);
        assertThat(attempt.getStatus()).isEqualTo(OtpStatus.PENDING);
    }

    @Test
    @DisplayName("verifyPasswordResetOtp does not accept an OTP issued for another purpose")
    void verifyPasswordResetOtp_otherPurpose_throwsInvalidOtp() {
        OtpRequestEntity loginAttempt = OtpRequestEntity.builder()
                .id(UUID.randomUUID())
                .email("patient@example.com")
                .verificationMode(VerificationMode.EMAIL)
                .hashedOtp("hashed-654321")
                .purpose(OtpPurpose.LOGIN)
                .status(OtpStatus.PENDING)
                .verificationAttempts(0)
                .expiresAt(Instant.now().plus(5, ChronoUnit.MINUTES))
                .build();
        when(otpRequestRepository.findTopByEmailAndStatusOrderByCreatedAtDesc("patient@example.com", OtpStatus.PENDING))
                .thenReturn(Optional.of(loginAttempt));

        assertThatThrownBy(() -> otpService.verifyPasswordResetOtp(sampleUser, "654321", "127.0.0.1"))
                .isInstanceOf(InvalidOtpException.class);
    }

    @Test
    @DisplayName("verifyPasswordResetOtp rejects a blank code")
    void verifyPasswordResetOtp_blankCode_throwsInvalidOtp() {
        assertThatThrownBy(() -> otpService.verifyPasswordResetOtp(sampleUser, " ", "127.0.0.1"))
                .isInstanceOf(InvalidOtpException.class);
    }
}
