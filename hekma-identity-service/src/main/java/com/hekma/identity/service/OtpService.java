package com.hekma.identity.service;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.OtpAuditEventType;
import com.hekma.identity.domain.otp.OtpAuditLogEntity;
import com.hekma.identity.domain.otp.OtpLockoutEntity;
import com.hekma.identity.domain.otp.OtpPurpose;
import com.hekma.identity.domain.otp.OtpRequestEntity;
import com.hekma.identity.domain.otp.OtpStatus;
import com.hekma.identity.domain.otp.VerificationMode;
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
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Service
@Slf4j
public class OtpService {

    private static final int OTP_VALIDITY_MINUTES = 5;
    private static final int LOCKOUT_DURATION_MINUTES = 30;
    private static final int MAX_HOURLY_REQUESTS = 5;
    private static final int MAX_RESENDS = 3;
    private static final int MAX_VERIFICATION_ATTEMPTS = 5;

    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final DateTimeFormatter TIME_FORMATTER = DateTimeFormatter.ofPattern("hh:mm a").withZone(ZoneId.systemDefault());

    private final OtpRequestRepository otpRequestRepository;
    private final OtpLockoutRepository otpLockoutRepository;
    private final OtpAuditLogRepository otpAuditLogRepository;
    private final PatientDetailRepository patientDetailRepository;
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final FirebaseService firebaseService;
    private final NotificationServiceClient notificationServiceClient;

    /**
     * When true, plaintext OTP codes are echoed to the console/log for local development.
     * Must be false in any shared or production environment.
     */
    private boolean consoleEcho = false;

    public OtpService(
            OtpRequestRepository otpRequestRepository,
            OtpLockoutRepository otpLockoutRepository,
            OtpAuditLogRepository otpAuditLogRepository,
            PatientDetailRepository patientDetailRepository,
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            FirebaseService firebaseService,
            NotificationServiceClient notificationServiceClient) {
        this.otpRequestRepository = otpRequestRepository;
        this.otpLockoutRepository = otpLockoutRepository;
        this.otpAuditLogRepository = otpAuditLogRepository;
        this.patientDetailRepository = patientDetailRepository;
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.firebaseService = firebaseService;
        this.notificationServiceClient = notificationServiceClient;
    }

    @Value("${app.otp.console-echo:false}")
    void setConsoleEcho(boolean consoleEcho) {
        this.consoleEcho = consoleEcho;
        if (!consoleEcho) {
            log.warn("OTP console echo is disabled. PHONE-mode OTPs are not delivered (no SMS integration configured).");
        }
    }

    /**
     * Prints a plaintext OTP for local development (app.otp.console-echo=true)
     * and unconditionally for PASSWORD_RESET (forgot-password workflow).
     */
    private void echoOtp(String label, String destination, String plainOtp) {
        boolean isPasswordReset = label != null && label.contains("PASSWORD_RESET");
        if (!consoleEcho && !isPasswordReset) {
            return;
        }
        System.out.println("==================================================================");
        if (isPasswordReset) {
            System.out.println(">>> [FORGOT PASSWORD OTP] Endpoint: /api/v1/auth/forgot-password");
            System.out.println(">>> Destination: " + destination + " | OTP: " + plainOtp + " <<<");
        } else {
            System.out.println(">>> [" + label + "] Destination: " + destination + " | OTP: " + plainOtp + " <<<");
        }
        System.out.println("==================================================================");
        log.info("[DEV_OTP_CONSOLE] [{}] Destination: {} | OTP: {}", label, destination, plainOtp);
    }

    /**
     * Generates and dispatches a 6-digit OTP for login, registration, or re-authentication.
     * Enforces hourly rate limiting (5 per hour) and 30-minute lockout.
     */
    @Transactional
    public SendOtpResponse sendOtp(SendOtpRequest request, String ipAddress) {
        VerificationMode mode = request.getVerificationMode() != null ? request.getVerificationMode() :
                (request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank() ? VerificationMode.PHONE : VerificationMode.EMAIL);
        String phoneNumber = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank() ? request.getPhoneNumber().trim() : null;
        String email = request.getEmail() != null && !request.getEmail().isBlank() ? request.getEmail().trim().toLowerCase() : null;
        OtpPurpose purpose = request.getPurpose() != null ? request.getPurpose() : OtpPurpose.LOGIN;

        if (mode == VerificationMode.PHONE && phoneNumber == null) {
            throw new IllegalArgumentException("Phone number is required when verification mode is PHONE");
        }
        if (mode == VerificationMode.EMAIL && email == null) {
            throw new IllegalArgumentException("Email is required when verification mode is EMAIL");
        }

        log.info("Initiating OTP generation for verification mode: {}, phone: {}, email: {}, purpose: {}", mode, phoneNumber, email, purpose);

        // Check if locked out or if hourly request limit is exceeded
        if (mode == VerificationMode.PHONE) {
            checkAndEnforceLockoutForPhone(phoneNumber, ipAddress);
        } else {
            checkAndEnforceLockoutForEmail(email, ipAddress);
        }

        // For LOGIN or RE_AUTHENTICATION, verify registered user account exists and is active
        if (purpose == OtpPurpose.LOGIN || purpose == OtpPurpose.RE_AUTHENTICATION) {
            Optional<UserEntity> userOpt = (mode == VerificationMode.PHONE)
                    ? findUserByPhone(phoneNumber)
                    : userRepository.findByEmail(email);

            if (userOpt.isEmpty()) {
                String identifier = mode == VerificationMode.PHONE ? phoneNumber : email;
                throw new InvalidTokenException("No registered account found with " + (mode == VerificationMode.PHONE ? "phone number " : "email ") + identifier);
            }
            if (userOpt.get().getStatus() != UserStatus.ACTIVE || !Boolean.TRUE.equals(userOpt.get().getIsActive())) {
                throw new UserInactiveException("Account is " + userOpt.get().getStatus().name().toLowerCase() + ". Authentication denied.");
            }
        }

        Instant now = Instant.now();
        String plainOtp = generateNumericOtp();
        String hashedOtp = passwordEncoder.encode(plainOtp);

        OtpRequestEntity otpEntity = OtpRequestEntity.builder()
                .phoneNumber(phoneNumber)
                .email(email)
                .verificationMode(mode)
                .hashedOtp(hashedOtp)
                .purpose(purpose)
                .status(OtpStatus.PENDING)
                .resendCount(0)
                .verificationAttempts(0)
                .expiresAt(now.plus(OTP_VALIDITY_MINUTES, ChronoUnit.MINUTES))
                .build();

        otpEntity = otpRequestRepository.save(otpEntity);

        String purposeLabel = (purpose != null) ? purpose.name() : "AUTH";
        if (mode == VerificationMode.PHONE) {
            // For PHONE mode: no SMS integration yet; the OTP is only echoed to the console in dev (app.otp.console-echo)
            echoOtp(purposeLabel + " OTP - PHONE", phoneNumber, plainOtp);
        } else {
            // For EMAIL mode: dispatch via hekma-notification-service (and echo to console in dev)
            echoOtp(purposeLabel + " OTP - EMAIL", email, plainOtp);
            notificationServiceClient.sendOtpEmail(email, plainOtp, otpEntity.getId());
        }

        // Audit log event
        recordAuditLog(phoneNumber, email, otpEntity.getId(), OtpAuditEventType.GENERATION,
                "Generated OTP for attempt " + otpEntity.getId() + " with purpose " + purpose + " via verification mode " + mode, ipAddress);

        return SendOtpResponse.builder()
                .attemptId(otpEntity.getId())
                .phoneNumber(phoneNumber)
                .email(email)
                .verificationMode(mode)
                .expiresInSeconds(OTP_VALIDITY_MINUTES * 60L)
                .message(mode == VerificationMode.PHONE
                        ? "OTP generated (printed to console for dev testing)."
                        : "OTP has been sent to your registered email address.")
                .build();
    }

    /**
     * Resends an OTP for an active authentication attempt.
     * Allows a maximum of 3 resends per attempt, resets OTP validity to 5 minutes, and checks hourly limits.
     */
    @Transactional
    public ResendOtpResponse resendOtp(ResendOtpRequest request, String ipAddress) {
        UUID attemptId = request.getAttemptId();
        String phoneNumber = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank() ? request.getPhoneNumber().trim() : null;
        String email = request.getEmail() != null && !request.getEmail().isBlank() ? request.getEmail().trim().toLowerCase() : null;

        log.info("Initiating OTP resend for attempt: {}, phone: {}, email: {}", attemptId, phoneNumber, email);

        OtpRequestEntity attempt = null;
        if (attemptId != null) {
            if (phoneNumber != null) {
                attempt = otpRequestRepository.findByIdAndPhoneNumber(attemptId, phoneNumber).orElse(null);
            } else if (email != null) {
                attempt = otpRequestRepository.findByIdAndEmail(attemptId, email).orElse(null);
            } else {
                attempt = otpRequestRepository.findById(attemptId).orElse(null);
            }
        }

        UUID targetUserId = request.getUserId() != null ? request.getUserId() : attemptId;
        if (attempt == null && targetUserId != null) {
            Optional<UserEntity> userOpt = userRepository.findById(targetUserId);
            if (userOpt.isPresent()) {
                UserEntity user = userOpt.get();
                if (user.getEmail() != null) {
                    attempt = otpRequestRepository.findTopByEmailAndStatusOrderByCreatedAtDesc(user.getEmail().toLowerCase(), OtpStatus.PENDING).orElse(null);
                }
                if (attempt == null && user.getPhoneNumber() != null) {
                    attempt = otpRequestRepository.findTopByPhoneNumberAndStatusOrderByCreatedAtDesc(user.getPhoneNumber(), OtpStatus.PENDING).orElse(null);
                }
            }
        }

        if (attempt == null && email != null) {
            attempt = otpRequestRepository.findTopByEmailOrderByCreatedAtDesc(email.toLowerCase()).orElse(null);
        }

        if (attempt == null && phoneNumber != null) {
            attempt = otpRequestRepository.findTopByPhoneNumberOrderByCreatedAtDesc(phoneNumber).orElse(null);
        }

        if (attempt == null && (email != null || phoneNumber != null)) {
            // No prior attempt found, but destination provided: dispatch fresh verification OTP
            SendOtpRequest sendReq = SendOtpRequest.builder()
                    .email(email)
                    .phoneNumber(phoneNumber)
                    .verificationMode(email != null ? VerificationMode.EMAIL : VerificationMode.PHONE)
                    .purpose(OtpPurpose.REGISTRATION)
                    .build();
            SendOtpResponse sent = sendOtp(sendReq, ipAddress);
            return ResendOtpResponse.builder()
                    .attemptId(sent.getAttemptId())
                    .phoneNumber(sent.getPhoneNumber())
                    .email(sent.getEmail())
                    .verificationMode(sent.getVerificationMode())
                    .resendCount(1)
                    .resendsRemaining(MAX_RESENDS - 1)
                    .expiresInSeconds(sent.getExpiresInSeconds())
                    .message("Verification code has been dispatched successfully.")
                    .build();
        }

        if (attempt == null) {
            throw new InvalidTokenException("Authentication attempt not found.");
        }

        VerificationMode mode = attempt.getVerificationMode() != null ? attempt.getVerificationMode() : VerificationMode.PHONE;

        // Check if locked out or if hourly request limit is exceeded
        if (mode == VerificationMode.PHONE && attempt.getPhoneNumber() != null) {
            checkAndEnforceLockoutForPhone(attempt.getPhoneNumber(), ipAddress);
        } else if (mode == VerificationMode.EMAIL && attempt.getEmail() != null) {
            checkAndEnforceLockoutForEmail(attempt.getEmail(), ipAddress);
        }

        if (attempt.getStatus() == OtpStatus.VERIFIED) {
            throw new InvalidOtpException("This authentication attempt has already been verified.");
        }

        if (attempt.getStatus() == OtpStatus.INVALIDATED) {
            throw new OtpVerificationLimitException("This authentication attempt was invalidated due to excessive failed attempts. Please initiate a new authentication attempt.");
        }

        if (attempt.getResendCount() >= MAX_RESENDS) {
            throw new OtpResendLimitException("Maximum OTP resend limit reached for this authentication attempt. Please initiate a new authentication attempt.");
        }

        Instant now = Instant.now();
        String plainOtp = generateNumericOtp();
        String hashedOtp = passwordEncoder.encode(plainOtp);

        int newResendCount = attempt.getResendCount() + 1;
        attempt.setHashedOtp(hashedOtp);
        attempt.setResendCount(newResendCount);
        attempt.setVerificationAttempts(0); // Reset attempts for the new OTP
        attempt.setExpiresAt(now.plus(OTP_VALIDITY_MINUTES, ChronoUnit.MINUTES));
        attempt.setStatus(OtpStatus.PENDING);

        otpRequestRepository.save(attempt);

        String resendLabel = (attempt.getPurpose() != null ? attempt.getPurpose().name() + " " : "") + "OTP RESEND - " + mode;
        if (mode == VerificationMode.PHONE) {
            echoOtp(resendLabel, attempt.getPhoneNumber(), plainOtp);
        } else {
            echoOtp(resendLabel, attempt.getEmail(), plainOtp);
            notificationServiceClient.sendOtpEmail(attempt.getEmail(), plainOtp, attempt.getId());
        }

        // Audit log event
        recordAuditLog(attempt.getPhoneNumber(), attempt.getEmail(), attempt.getId(), OtpAuditEventType.RESEND,
                "Resent OTP for attempt " + attempt.getId() + ". Resend count: " + newResendCount + "/" + MAX_RESENDS, ipAddress);

        int resendsRemaining = MAX_RESENDS - newResendCount;

        return ResendOtpResponse.builder()
                .attemptId(attempt.getId())
                .phoneNumber(attempt.getPhoneNumber())
                .email(attempt.getEmail())
                .verificationMode(mode)
                .resendCount(newResendCount)
                .resendsRemaining(resendsRemaining)
                .expiresInSeconds(OTP_VALIDITY_MINUTES * 60L)
                .message(mode == VerificationMode.PHONE
                        ? "OTP has been resent (printed to console for dev testing)."
                        : "OTP has been resent successfully.")
                .build();
    }

    /**
     * Verifies the submitted OTP code.
     * Enforces 5-minute expiration and a maximum of 5 verification attempts.
     */
    @Transactional
    public VerifyOtpResponse verifyOtp(VerifyOtpRequest request, String ipAddress) {
        UUID attemptId = request.getAttemptId();
        String phoneNumber = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank() ? request.getPhoneNumber().trim() : null;
        String email = request.getEmail() != null && !request.getEmail().isBlank() ? request.getEmail().trim().toLowerCase() : null;
        String submittedOtp = request.getOtpCode().trim();

        log.info("Verifying OTP for attempt: {}, userId: {}, phone: {}, email: {}", attemptId, request.getUserId(), phoneNumber, email);

        OtpRequestEntity attempt = null;
        if (attemptId != null) {
            if (phoneNumber != null) {
                attempt = otpRequestRepository.findByIdAndPhoneNumber(attemptId, phoneNumber).orElse(null);
            } else if (email != null) {
                attempt = otpRequestRepository.findByIdAndEmail(attemptId, email).orElse(null);
            } else {
                attempt = otpRequestRepository.findById(attemptId).orElse(null);
            }
        }

        UUID targetUserId = request.getUserId() != null ? request.getUserId() : attemptId;
        if (attempt == null && targetUserId != null) {
            Optional<UserEntity> userOpt = userRepository.findById(targetUserId);
            if (userOpt.isPresent()) {
                UserEntity user = userOpt.get();
                if (user.getEmail() != null) {
                    attempt = otpRequestRepository.findTopByEmailAndStatusOrderByCreatedAtDesc(user.getEmail().toLowerCase(), OtpStatus.PENDING).orElse(null);
                }
                if (attempt == null && user.getPhoneNumber() != null) {
                    attempt = otpRequestRepository.findTopByPhoneNumberAndStatusOrderByCreatedAtDesc(user.getPhoneNumber(), OtpStatus.PENDING).orElse(null);
                }
            }
        }

        if (attempt == null && email != null) {
            attempt = otpRequestRepository.findTopByEmailAndStatusOrderByCreatedAtDesc(email.toLowerCase(), OtpStatus.PENDING)
                    .or(() -> otpRequestRepository.findTopByEmailOrderByCreatedAtDesc(email.toLowerCase()))
                    .orElse(null);
        }

        if (attempt == null && phoneNumber != null) {
            attempt = otpRequestRepository.findTopByPhoneNumberAndStatusOrderByCreatedAtDesc(phoneNumber, OtpStatus.PENDING)
                    .or(() -> otpRequestRepository.findTopByPhoneNumberOrderByCreatedAtDesc(phoneNumber))
                    .orElse(null);
        }

        if (attempt == null) {
            throw new InvalidTokenException("Authentication attempt not found.");
        }

        String phone = attempt.getPhoneNumber();
        String mail = attempt.getEmail();

        consumeAttempt(attempt, submittedOtp, ipAddress);

        // Fetch user information if user is registered
        Optional<UserEntity> userOpt = Optional.empty();
        if (targetUserId != null) {
            userOpt = userRepository.findById(targetUserId);
        }
        if (userOpt.isEmpty() && phone != null) {
            userOpt = findUserByPhone(phone);
        }
        if (userOpt.isEmpty() && mail != null) {
            userOpt = userRepository.findByEmail(mail);
        }

        VerificationMode verifiedMode = attempt.getVerificationMode() != null ? attempt.getVerificationMode() : VerificationMode.PHONE;

        if (userOpt.isPresent()) {
            UserEntity user = userOpt.get();

            if (user.getStatus() == UserStatus.SUSPENDED || user.getStatus() == UserStatus.INACTIVE) {
                throw new UserInactiveException("Account is suspended or inactive. Authentication denied.");
            }

            boolean newlyActivated = false;
            if (user.getStatus() == UserStatus.PENDING_VERIFICATION) {
                user.setStatus(UserStatus.ACTIVE);
                user.setIsActive(true);
                newlyActivated = true;
                // A self-registered tenant is activated by its owner's verification.
                if (user.getTenant() != null && user.getTenant().getStatus() == TenantStatus.PENDING_VERIFICATION) {
                    user.getTenant().setStatus(TenantStatus.ACTIVE);
                    log.info("Tenant {} activated by owner verification.", user.getTenant().getSlug());
                }
            } else if (!Boolean.TRUE.equals(user.getIsActive())) {
                throw new UserInactiveException("Account is suspended or inactive. Authentication denied.");
            }

            // Update verification status and verification mode on user entity
            user.setVerificationMode(verifiedMode);
            if (verifiedMode == VerificationMode.PHONE) {
                user.setPhoneVerified(true);
            } else if (verifiedMode == VerificationMode.EMAIL) {
                user.setEmailVerified(true);
            }

            user = userRepository.save(user);
            if (newlyActivated) {
                log.info("User {} activated upon successful OTP verification.", user.getEmail() != null ? user.getEmail() : user.getPhoneNumber());
            }

            Map<String, Object> claims = new HashMap<>();
            claims.put("role", user.getRole().name());
            if (user.getTenant() != null && user.getTenant().getId() != null) {
                claims.put("tenantId", user.getTenant().getId().toString());
            }
            String customToken = firebaseService.createCustomToken(user.getFirebaseUid(), claims);
            FirebaseSignInResponse session = firebaseService.signInWithCustomToken(customToken);

            String displayName = user.getDisplayName();
            if ((displayName == null || displayName.isBlank()) && phone != null) {
                displayName = patientDetailRepository.findByPhoneNumber(phone)
                        .map(p -> p.getFirstName() + " " + p.getLastName())
                        .orElse(null);
            }

            String successMessage = newlyActivated
                    ? "OTP verified successfully. Account activated."
                    : "OTP verified successfully.";

            String resolvedPhone = user.getPhoneNumber() != null ? user.getPhoneNumber() : phone;

            return VerifyOtpResponse.builder()
                    .verified(true)
                    .attemptId(attempt.getId())
                    .phoneNumber(resolvedPhone)
                    .email(user.getEmail() != null ? user.getEmail() : mail)
                    .phoneVerified(user.getPhoneVerified())
                    .emailVerified(user.getEmailVerified())
                    .twoFactorEnabled(Boolean.TRUE.equals(user.getTwoFactorEnabled()))
                    .verificationMode(user.getVerificationMode())
                    .firebaseCustomToken(customToken)
                    .idToken(session.getIdToken())
                    .refreshToken(session.getRefreshToken())
                    .tokenType("Bearer")
                    .expiresIn(session.getExpiresIn())
                    .userId(user.getId())
                    .firebaseUid(user.getFirebaseUid())
                    .role(user.getRole())
                    .displayName(displayName)
                    .tenantId(user.getTenant() != null ? user.getTenant().getId() : null)
                    .tenantSlug(user.getTenant() != null ? user.getTenant().getSlug() : null)
                    .status(user.getStatus() != null ? user.getStatus().name() : "ACTIVE")
                    .message(successMessage)
                    .build();
        }

        // If user not registered yet (e.g. standalone phone verification)
        return VerifyOtpResponse.builder()
                .verified(true)
                .attemptId(attempt.getId())
                .phoneNumber(phone)
                .email(mail)
                .phoneVerified(verifiedMode == VerificationMode.PHONE)
                .emailVerified(verifiedMode == VerificationMode.EMAIL)
                .twoFactorEnabled(false)
                .verificationMode(verifiedMode)
                .message("OTP verified successfully.")
                .build();
    }

    /**
     * Verifies a password-reset OTP for the given user. The most recent pending PASSWORD_RESET attempt
     * for the user's email or phone is checked, with the same expiry, attempt-limit and audit rules as
     * {@link #verifyOtp}. No tokens are issued.
     *
     * @throws InvalidOtpException if no pending reset code exists or the code does not match
     */
    @Transactional(noRollbackFor = {InvalidOtpException.class, OtpExpiredException.class, OtpVerificationLimitException.class})
    public void verifyPasswordResetOtp(UserEntity user, String submittedOtp, String ipAddress) {
        if (submittedOtp == null || submittedOtp.isBlank()) {
            throw new InvalidOtpException("Verification code is required.");
        }

        Optional<OtpRequestEntity> attemptOpt = Optional.empty();
        if (user.getEmail() != null) {
            attemptOpt = otpRequestRepository.findTopByEmailAndStatusOrderByCreatedAtDesc(user.getEmail().toLowerCase(), OtpStatus.PENDING)
                    .filter(a -> a.getPurpose() == OtpPurpose.PASSWORD_RESET);
        }
        if (attemptOpt.isEmpty() && user.getPhoneNumber() != null) {
            attemptOpt = otpRequestRepository.findTopByPhoneNumberAndStatusOrderByCreatedAtDesc(user.getPhoneNumber(), OtpStatus.PENDING)
                    .filter(a -> a.getPurpose() == OtpPurpose.PASSWORD_RESET);
        }

        OtpRequestEntity attempt = attemptOpt
                .orElseThrow(() -> new InvalidOtpException("Invalid or expired verification code."));
        consumeAttempt(attempt, submittedOtp.trim(), ipAddress);
    }

    /**
     * Checks a submitted code against an attempt (status, attempt limit, expiry, hash) and marks it VERIFIED.
     */
    private void consumeAttempt(OtpRequestEntity attempt, String submittedOtp, String ipAddress) {
        String phone = attempt.getPhoneNumber();
        String mail = attempt.getEmail();

        if (attempt.getStatus() == OtpStatus.VERIFIED) {
            throw new InvalidOtpException("OTP has already been verified for this attempt.");
        }

        if (attempt.getStatus() == OtpStatus.INVALIDATED || attempt.getVerificationAttempts() >= MAX_VERIFICATION_ATTEMPTS) {
            throw new OtpVerificationLimitException("Maximum verification attempts exceeded. This OTP is invalid. Please request a new OTP.");
        }

        Instant now = Instant.now();

        // Check expiration
        if (now.isAfter(attempt.getExpiresAt())) {
            attempt.setStatus(OtpStatus.EXPIRED);
            otpRequestRepository.save(attempt);

            recordAuditLog(phone, mail, attempt.getId(), OtpAuditEventType.EXPIRATION,
                    "OTP expired for attempt " + attempt.getId() + " during verification", ipAddress);

            throw new OtpExpiredException("OTP has expired. Please request a new OTP.");
        }

        // Verify hash
        boolean matches = passwordEncoder.matches(submittedOtp, attempt.getHashedOtp());

        if (!matches) {
            int newAttempts = attempt.getVerificationAttempts() + 1;
            attempt.setVerificationAttempts(newAttempts);

            if (newAttempts >= MAX_VERIFICATION_ATTEMPTS) {
                attempt.setStatus(OtpStatus.INVALIDATED);
                otpRequestRepository.save(attempt);

                recordAuditLog(phone, mail, attempt.getId(), OtpAuditEventType.VERIFICATION_FAILURE,
                        "Maximum verification attempts exceeded (" + newAttempts + "/" + MAX_VERIFICATION_ATTEMPTS + "). OTP invalidated.", ipAddress);

                throw new OtpVerificationLimitException("Maximum verification attempts exceeded. This OTP is now invalid. Please request a new OTP.");
            } else {
                otpRequestRepository.save(attempt);

                int remainingAttempts = MAX_VERIFICATION_ATTEMPTS - newAttempts;
                recordAuditLog(phone, mail, attempt.getId(), OtpAuditEventType.VERIFICATION_FAILURE,
                        "Incorrect OTP entered. " + remainingAttempts + " attempts remaining.", ipAddress);

                throw new InvalidOtpException("Invalid OTP code. " + remainingAttempts + " attempts remaining.");
            }
        }

        // Verification successful
        attempt.setStatus(OtpStatus.VERIFIED);
        attempt.setVerifiedAt(now);
        otpRequestRepository.save(attempt);

        recordAuditLog(phone, mail, attempt.getId(), OtpAuditEventType.VERIFICATION_SUCCESS,
                "OTP verified successfully for attempt " + attempt.getId(), ipAddress);
    }

    /**
     * Finds a user by phone number from the users table, falling back to patient_details if needed.
     */
    public Optional<UserEntity> findUserByPhone(String phoneNumber) {
        Optional<UserEntity> userOpt = userRepository.findByPhoneNumber(phoneNumber);
        if (userOpt.isPresent()) {
            return userOpt;
        }
        return patientDetailRepository.findByPhoneNumber(phoneNumber).map(PatientDetailEntity::getUser);
    }

    /**
     * Helper to verify if the phone number is currently locked out or has exceeded the hourly limit.
     */
    private void checkAndEnforceLockoutForPhone(String phoneNumber, String ipAddress) {
        Instant now = Instant.now();

        // 1. Check existing active lockout
        Optional<OtpLockoutEntity> lockoutOpt = otpLockoutRepository.findByPhoneNumber(phoneNumber);
        if (lockoutOpt.isPresent()) {
            OtpLockoutEntity lockout = lockoutOpt.get();
            if (now.isBefore(lockout.getLockedUntil())) {
                String timeStr = formatLockoutTime(lockout.getLockedUntil());
                throw new OtpLockoutException("Your OTP limit is reached, please come back at " + timeStr + " or after 30 mins", lockout.getLockedUntil());
            } else {
                // Lockout period has elapsed; clear the lockout record
                otpLockoutRepository.delete(lockout);
            }
        }

        // 2. Check hourly requests limit (5 OTPs per hour)
        Instant oneHourAgo = now.minus(1, ChronoUnit.HOURS);
        long totalRequestsInLastHour = otpRequestRepository.countTotalOtpRequestsInWindow(phoneNumber, oneHourAgo);

        if (totalRequestsInLastHour >= MAX_HOURLY_REQUESTS) {
            Instant lockedUntil = now.plus(LOCKOUT_DURATION_MINUTES, ChronoUnit.MINUTES);
            OtpLockoutEntity newLockout = OtpLockoutEntity.builder()
                    .phoneNumber(phoneNumber)
                    .lockedUntil(lockedUntil)
                    .lockReason("Hourly OTP request limit exceeded (max " + MAX_HOURLY_REQUESTS + " per hour)")
                    .build();
            otpLockoutRepository.save(newLockout);

            recordAuditLog(phoneNumber, null, null, OtpAuditEventType.LOCKOUT,
                    "User locked out for " + LOCKOUT_DURATION_MINUTES + " minutes until " + lockedUntil + " due to exceeding hourly OTP limit", ipAddress);

            String timeStr = formatLockoutTime(lockedUntil);
            throw new OtpLockoutException("Your OTP limit is reached, please come back at " + timeStr + " or after 30 mins", lockedUntil);
        }
    }

    /**
     * Helper to verify if the email is currently locked out or has exceeded the hourly limit.
     */
    private void checkAndEnforceLockoutForEmail(String email, String ipAddress) {
        Instant now = Instant.now();

        // 1. Check existing active lockout
        Optional<OtpLockoutEntity> lockoutOpt = otpLockoutRepository.findByEmail(email);
        if (lockoutOpt.isPresent()) {
            OtpLockoutEntity lockout = lockoutOpt.get();
            if (now.isBefore(lockout.getLockedUntil())) {
                String timeStr = formatLockoutTime(lockout.getLockedUntil());
                throw new OtpLockoutException("Your OTP limit is reached, please come back at " + timeStr + " or after 30 mins", lockout.getLockedUntil());
            } else {
                // Lockout period has elapsed; clear the lockout record
                otpLockoutRepository.delete(lockout);
            }
        }

        // 2. Check hourly requests limit (5 OTPs per hour)
        Instant oneHourAgo = now.minus(1, ChronoUnit.HOURS);
        long totalRequestsInLastHour = otpRequestRepository.countTotalOtpRequestsInWindowByEmail(email, oneHourAgo);

        if (totalRequestsInLastHour >= MAX_HOURLY_REQUESTS) {
            Instant lockedUntil = now.plus(LOCKOUT_DURATION_MINUTES, ChronoUnit.MINUTES);
            OtpLockoutEntity newLockout = OtpLockoutEntity.builder()
                    .email(email)
                    .lockedUntil(lockedUntil)
                    .lockReason("Hourly OTP request limit exceeded (max " + MAX_HOURLY_REQUESTS + " per hour)")
                    .build();
            otpLockoutRepository.save(newLockout);

            recordAuditLog(null, email, null, OtpAuditEventType.LOCKOUT,
                    "User locked out for " + LOCKOUT_DURATION_MINUTES + " minutes until " + lockedUntil + " due to exceeding hourly OTP limit", ipAddress);

            String timeStr = formatLockoutTime(lockedUntil);
            throw new OtpLockoutException("Your OTP limit is reached, please come back at " + timeStr + " or after 30 mins", lockedUntil);
        }
    }

    private void recordAuditLog(String phoneNumber, String email, UUID attemptId, OtpAuditEventType eventType, String message, String ipAddress) {
        try {
            OtpAuditLogEntity auditLog = OtpAuditLogEntity.builder()
                    .phoneNumber(phoneNumber)
                    .email(email)
                    .attemptId(attemptId)
                    .eventType(eventType)
                    .message(message)
                    .ipAddress(ipAddress)
                    .createdAt(Instant.now())
                    .build();
            otpAuditLogRepository.save(auditLog);
        } catch (Exception e) {
            log.error("Failed to record OTP audit log for phone {} / email {}: {}", phoneNumber, email, e.getMessage());
        }
    }

    private String generateNumericOtp() {
        int code = SECURE_RANDOM.nextInt(1_000_000);
        return String.format("%06d", code);
    }

    private String formatLockoutTime(Instant instant) {
        return TIME_FORMATTER.format(instant);
    }
}
