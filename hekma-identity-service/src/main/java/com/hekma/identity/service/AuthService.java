package com.hekma.identity.service;

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
import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.exception.InvalidRoleException;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.exception.TenantSuspendedException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.exception.UserInactiveException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseSignInResponse;
import com.hekma.identity.firebase.FirebaseTokenRefreshResponse;
import com.hekma.identity.firebase.FirebaseUserDto;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.AuthEmails;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

@Service
@Slf4j
public class AuthService {

    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final String UPPERCASE = "ABCDEFGHJKLMNPQRSTUVWXYZ";
    private static final String LOWERCASE = "abcdefghijkmnopqrstuvwxyz";
    private static final String DIGITS = "23456789";
    private static final String SYMBOLS = "!@#$%^&*()-_=+";
    private static final String PASSWORD_RESET_DISPATCHED_MESSAGE =
            "If an account matches this identifier, a password reset code has been dispatched.";

    private final UserRepository userRepository;
    private final FirebaseService firebaseService;
    private final OtpService otpService;
    private final NotificationServiceClient notificationServiceClient;
    private final com.hekma.identity.repository.TenantRepository tenantRepository;
    private final com.hekma.identity.repository.PatientDetailRepository patientDetailRepository;
    private final AuthorityService authorityService;
    private final RoleAuthorityService roleAuthorityService;
    private final AuditService auditService;

    public AuthService(UserRepository userRepository,
                       FirebaseService firebaseService,
                       OtpService otpService,
                       NotificationServiceClient notificationServiceClient,
                       com.hekma.identity.repository.TenantRepository tenantRepository,
                       com.hekma.identity.repository.PatientDetailRepository patientDetailRepository,
                       AuthorityService authorityService,
                       RoleAuthorityService roleAuthorityService,
                       AuditService auditService) {
        this.userRepository = userRepository;
        this.firebaseService = firebaseService;
        this.otpService = otpService;
        this.notificationServiceClient = notificationServiceClient;
        this.tenantRepository = tenantRepository;
        this.patientDetailRepository = patientDetailRepository;
        this.authorityService = authorityService;
        this.roleAuthorityService = roleAuthorityService;
        this.auditService = auditService;
    }


    /**
     * Public self-registration for PATIENT accounts.
     * The patient joins the default tenant (Hekma), or the tenant of a valid patient invitation code.
     * SPONSOR/SITE accounts are created by tenant registration or invitation, never by joining an existing tenant.
     * Enforces OTP verification and sets initial status to PENDING_VERIFICATION.
     */
    public RegisterResponse register(RegisterRequest request) {
        return register(request, null);
    }

    public RegisterResponse register(RegisterRequest request, String clientIp) {
        Role role = request.getRole();
        if (role == null || !role.isPubliclyRegisterable()) {
            throw new InvalidRoleException("Role '" + role + "' is not permitted for public self-registration. Only PATIENT accounts can self-register.");
        }

        String normalizedEmail = request.getEmail() != null && !request.getEmail().isBlank()
                ? request.getEmail().trim().toLowerCase() : null;
        String normalizedPhone = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank()
                ? request.getPhoneNumber().trim() : null;

        if (normalizedEmail == null && normalizedPhone == null) {
            throw new IllegalArgumentException("At least one of email or phone number is required for registration.");
        }

        VerificationMode verificationMode = request.getVerificationMode();
        if (verificationMode == null) {
            verificationMode = (normalizedPhone != null) ? VerificationMode.PHONE : VerificationMode.EMAIL;
        }

        if (verificationMode == VerificationMode.PHONE && normalizedPhone == null) {
            throw new IllegalArgumentException("Phone number is required when verification mode is PHONE.");
        }
        if (verificationMode == VerificationMode.EMAIL && normalizedEmail == null) {
            throw new IllegalArgumentException("Email is required when verification mode is EMAIL.");
        }

        if (normalizedEmail != null && userRepository.existsByEmail(normalizedEmail)) {
            throw new UserAlreadyExistsException("A user with email '" + normalizedEmail + "' is already registered in the system.");
        }

        if (normalizedPhone != null && userRepository.existsByPhoneNumber(normalizedPhone)) {
            throw new UserAlreadyExistsException("A user with phone number '" + normalizedPhone + "' is already registered in the system.");
        }

        if (normalizedEmail != null) {
            Optional<FirebaseUserDto> existingFbUser = firebaseService.getUserByEmail(normalizedEmail);
            if (existingFbUser.isPresent()) {
                throw new UserAlreadyExistsException("A user with email '" + normalizedEmail + "' already exists in Firebase.");
            }
        }

        // Resolve tenant: the inviting tenant for a valid invitation code, otherwise the default tenant (Hekma).
        com.hekma.identity.domain.TenantEntity tenant = null;
        UserEntity stagedAssignedUser = null;
        if (request.getInvitationCode() != null && !request.getInvitationCode().isBlank()) {
            Optional<PatientDetailEntity> stagedInvite = patientDetailRepository.findByInvitationCode(request.getInvitationCode().trim());
            if (stagedInvite.isPresent()) {
                PatientDetailEntity stagedDetail = stagedInvite.get();
                PatientService.requireUsableInvitation(stagedDetail);
                stagedDetail.setInvitationUsedAt(Instant.now());
                patientDetailRepository.save(stagedDetail);
                stagedAssignedUser = stagedDetail.getAssignedUser();
                tenant = stagedDetail.getUser() != null ? stagedDetail.getUser().getTenant() : null;
            }
        }
        if (tenant == null) {
            tenant = tenantRepository.findByDefaultTenantTrue()
                    .orElseGet(() -> tenantRepository.findBySlug("default-tenant").orElse(null));
        }
        if (tenant != null && tenant.getStatus() == com.hekma.identity.domain.TenantStatus.SUSPENDED) {
            throw new TenantSuspendedException("Tenant organization '" + tenant.getName() + "' is suspended. Registration denied.");
        }

        String authEmail = AuthEmails.resolve(normalizedEmail);
        FirebaseUserDto firebaseUser = firebaseService.createUser(authEmail, request.getPassword(), request.getDisplayName(), role);
        if (tenant != null) {
            firebaseService.assignClaims(firebaseUser.getUid(), role, tenant.getId());
        }

        UserEntity userEntity;
        try {
            userEntity = UserEntity.builder()
                    .firebaseUid(firebaseUser.getUid())
                    .email(normalizedEmail)
                    .authEmail(authEmail)
                    .role(role)
                    .displayName(request.getDisplayName() != null ? request.getDisplayName().trim() : null)
                    .phoneNumber(normalizedPhone)
                    .status(UserStatus.PENDING_VERIFICATION)
                    .isActive(false)
                    .isDeleted(false)
                    .phoneVerified(false)
                    .emailVerified(false)
                    .twoFactorEnabled(false)
                    .verificationMode(verificationMode)
                    .tenant(tenant)
                    .build();

            userEntity = userRepository.save(userEntity);

            if (role == Role.PATIENT) {
                String firstName = "Patient";
                String lastName = "";
                if (request.getDisplayName() != null && !request.getDisplayName().isBlank()) {
                    String[] parts = request.getDisplayName().trim().split("\\s+", 2);
                    firstName = parts[0];
                    lastName = parts.length > 1 ? parts[1] : "";
                }
                PatientDetailEntity patientDetail = PatientDetailEntity.builder()
                        .user(userEntity)
                        .firstName(firstName)
                        .lastName(lastName)
                        .phoneNumber(normalizedPhone)
                        .invitationCode(request.getInvitationCode() != null ? request.getInvitationCode().trim() : null)
                        .termsAccepted(true)
                        .privacyPolicyAccepted(true)
                        .healthDataConsentAccepted(true)
                        .consentedAt(Instant.now())
                        .assignedUser(stagedAssignedUser)
                        .build();
                patientDetailRepository.save(patientDetail);
            }
        } catch (Exception e) {
            log.error("Failed to persist user {} to database. Performing compensating rollback in Firebase: {}", normalizedEmail, e.getMessage());
            firebaseService.deleteUser(firebaseUser.getUid());
            throw e;
        }


        SendOtpResponse otpResponse = null;
        try {
            SendOtpRequest otpRequest = SendOtpRequest.builder()
                    .phoneNumber(normalizedPhone)
                    .email(normalizedEmail)
                    .verificationMode(verificationMode)
                    .purpose(OtpPurpose.REGISTRATION)
                    .build();
            otpResponse = otpService.sendOtp(otpRequest, clientIp);
        } catch (Exception e) {
            log.error("Failed to dispatch registration OTP. Performing compensating rollback: {}", e.getMessage());
            userRepository.delete(userEntity);
            firebaseService.deleteUser(firebaseUser.getUid());
            throw e;
        }

        // Asynchronously dispatch Welcome Email and In-App notification via hekma-notification-service
        try {
            if (userEntity.getEmail() != null) {
                notificationServiceClient.sendWelcomeEmail(userEntity.getEmail(), userEntity.getDisplayName());
            }
            notificationServiceClient.sendWelcomeInApp(userEntity.getId(), userEntity.getDisplayName());
        } catch (Exception e) {
            log.warn("Failed to dispatch welcome notifications for registered user {}: {}", userEntity.getId(), e.getMessage());
        }

        String successMessage = verificationMode == VerificationMode.PHONE
                ? "User registered successfully. An OTP has been generated for phone verification."
                : "User registered successfully. An OTP has been sent to your email address for verification.";

        return RegisterResponse.builder()
                .id(userEntity.getId())
                .firebaseUid(userEntity.getFirebaseUid())
                .email(userEntity.getEmail())
                .role(userEntity.getRole())
                .displayName(userEntity.getDisplayName())
                .phoneNumber(userEntity.getPhoneNumber())
                .status(userEntity.getStatus())
                .phoneVerified(userEntity.getPhoneVerified())
                .emailVerified(userEntity.getEmailVerified())
                .twoFactorEnabled(userEntity.getTwoFactorEnabled())
                .verificationMode(userEntity.getVerificationMode())
                .otpAttemptId(otpResponse != null ? otpResponse.getAttemptId() : null)
                .otpExpiresInSeconds(otpResponse != null ? otpResponse.getExpiresInSeconds() : null)
                .createdAt(userEntity.getCreatedAt())
                .message(successMessage)
                .tenantId(userEntity.getTenantId())
                .tenantSlug(userEntity.getTenant() != null ? userEntity.getTenant().getSlug() : null)
                .build();
    }


    /**
     * Public self-registration of a new top-level tenant (organization) together with its owner user (OD-1).
     * The owner's role equals the tenant type (SPONSOR or SITE). Tenant and owner stay PENDING_VERIFICATION until
     * the owner verifies the OTP (POST /api/v1/auth/otp/verify), which activates both.
     * <p>
     * Dual-write saga: the Firebase account is created first; if any later step fails (database or OTP dispatch),
     * the Firebase account is deleted and the database changes roll back.
     */
    @Transactional
    public com.hekma.identity.dto.tenant.RegisterTenantResponse registerTenant(
            com.hekma.identity.dto.tenant.RegisterTenantRequest request, String clientIp) {
        Role role = request.getTenantType() != null ? request.getTenantType().staffRole() : null;
        if (role == null) {
            throw new InvalidRoleException("Organization type must be SPONSOR or SITE.");
        }

        String slug = request.getTenantSlug().trim().toLowerCase();
        if (tenantRepository.existsBySlug(slug)) {
            throw new IllegalArgumentException("An organization with slug '" + slug + "' already exists.");
        }

        String normalizedEmail = request.getEmail() != null && !request.getEmail().isBlank()
                ? request.getEmail().trim().toLowerCase() : null;
        String normalizedPhone = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank()
                ? request.getPhoneNumber().trim() : null;
        if (normalizedEmail == null && normalizedPhone == null) {
            throw new IllegalArgumentException("At least one of email or phone number is required for registration.");
        }

        VerificationMode verificationMode = request.getVerificationMode() != null
                ? request.getVerificationMode()
                : (normalizedPhone != null ? VerificationMode.PHONE : VerificationMode.EMAIL);
        if (verificationMode == VerificationMode.PHONE && normalizedPhone == null) {
            throw new IllegalArgumentException("Phone number is required when verification mode is PHONE.");
        }
        if (verificationMode == VerificationMode.EMAIL && normalizedEmail == null) {
            throw new IllegalArgumentException("Email is required when verification mode is EMAIL.");
        }

        if (normalizedEmail != null && (userRepository.existsByEmail(normalizedEmail)
                || firebaseService.getUserByEmail(normalizedEmail).isPresent())) {
            throw new UserAlreadyExistsException("A user with email '" + normalizedEmail + "' is already registered in the system.");
        }
        if (normalizedPhone != null && userRepository.existsByPhoneNumber(normalizedPhone)) {
            throw new UserAlreadyExistsException("A user with phone number '" + normalizedPhone + "' is already registered in the system.");
        }

        String authEmail = AuthEmails.resolve(normalizedEmail);
        String displayName = request.getDisplayName() != null ? request.getDisplayName().trim() : null;
        FirebaseUserDto firebaseUser = firebaseService.createUser(authEmail, request.getPassword(), displayName, role);

        try {
            com.hekma.identity.domain.TenantEntity tenant = tenantRepository.save(com.hekma.identity.domain.TenantEntity.builder()
                    .name(request.getTenantName().trim())
                    .slug(slug)
                    .tenantType(request.getTenantType())
                    .defaultTenant(false)
                    .status(com.hekma.identity.domain.TenantStatus.PENDING_VERIFICATION)
                    .subscriptionTier("STANDARD")
                    .contactEmail(normalizedEmail)
                    .contactPhone(normalizedPhone)
                    .build());

            firebaseService.assignClaims(firebaseUser.getUid(), role, tenant.getId());

            UserEntity owner = userRepository.save(UserEntity.builder()
                    .firebaseUid(firebaseUser.getUid())
                    .email(normalizedEmail)
                    .authEmail(authEmail)
                    .role(role)
                    .displayName(displayName)
                    .phoneNumber(normalizedPhone)
                    .status(UserStatus.PENDING_VERIFICATION)
                    .isActive(false)
                    .isDeleted(false)
                    .phoneVerified(false)
                    .emailVerified(false)
                    .twoFactorEnabled(false)
                    .verificationMode(verificationMode)
                    .tenant(tenant)
                    .build());

            authorityService.grantInitial(owner, roleAuthorityService.getRoleAuthorities(role), null);
            auditService.record(null, AuditService.TENANT_REGISTERED, AuditService.TARGET_TENANT,
                    tenant.getId(), tenant.getId(), null, tenant.getTenantType() + " owner " + owner.getId(), null);

            SendOtpResponse otpResponse = otpService.sendOtp(SendOtpRequest.builder()
                    .phoneNumber(normalizedPhone)
                    .email(normalizedEmail)
                    .verificationMode(verificationMode)
                    .purpose(OtpPurpose.REGISTRATION)
                    .build(), clientIp);

            log.info("Tenant '{}' ({}) self-registered with owner {} ({}); awaiting OTP verification.",
                    tenant.getSlug(), tenant.getTenantType(), owner.getId(), role);

            return com.hekma.identity.dto.tenant.RegisterTenantResponse.builder()
                    .tenantId(tenant.getId())
                    .tenantName(tenant.getName())
                    .tenantSlug(tenant.getSlug())
                    .tenantType(tenant.getTenantType())
                    .tenantStatus(tenant.getStatus())
                    .userId(owner.getId())
                    .email(owner.getEmail())
                    .phoneNumber(owner.getPhoneNumber())
                    .displayName(owner.getDisplayName())
                    .role(owner.getRole())
                    .status(owner.getStatus())
                    .otpAttemptId(otpResponse != null ? otpResponse.getAttemptId() : null)
                    .otpExpiresInSeconds(otpResponse != null ? otpResponse.getExpiresInSeconds() : null)
                    .verificationMode(verificationMode)
                    .message("Organization registered. Verify the OTP to activate the organization and its owner account.")
                    .build();
        } catch (RuntimeException e) {
            log.error("Tenant registration for slug '{}' failed. Performing compensating rollback in Firebase: {}", slug, e.getMessage());
            firebaseService.deleteUser(firebaseUser.getUid());
            throw e;
        }
    }

    /**
     * System Admin creates/invites an ADMIN user.
     */
    public RegisterResponse inviteAdmin(InviteAdminRequest request, java.util.UUID actorId) {
        RegisterResponse response = createUserWithRole(request.getEmail(), request.getTemporaryPassword(), request.getDisplayName(), Role.ADMIN, "Admin user invited successfully.");
        UserEntity adminUser = userRepository.findById(response.getId()).orElse(null);
        if (adminUser != null) {
            authorityService.grantInitial(adminUser, roleAuthorityService.getRoleAuthorities(Role.ADMIN), actorId);
        }
        auditService.record(actorId, AuditService.ADMIN_CREATED, AuditService.TARGET_USER, response.getId(), null, null, "ADMIN", null);
        return response;
    }

    /**
     * Refreshes an expired Firebase ID token using an OAuth2 refresh token.
     * Verifies that the associated user exists in PostgreSQL and is in ACTIVE status.
     *
     * @param request RefreshTokenRequest containing the refresh token
     * @return RefreshTokenResponse with new ID token, refresh token, and user details
     */
    public RefreshTokenResponse refreshToken(RefreshTokenRequest request) {
        String refreshToken = request.getRefreshToken();
        if (refreshToken == null || refreshToken.trim().isEmpty()) {
            throw new InvalidTokenException("Refresh token must not be blank.");
        }

        FirebaseTokenRefreshResponse fbResponse = firebaseService.refreshToken(refreshToken.trim());

        Optional<UserEntity> userOpt = userRepository.findByFirebaseUid(fbResponse.getFirebaseUid());
        if (userOpt.isEmpty()) {
            log.warn("Refresh token belongs to Firebase UID {} which has no record in the local database.", fbResponse.getFirebaseUid());
            throw new InvalidTokenException("No registered user found associated with this token.");
        }

        UserEntity user = userOpt.get();
        if (user.getStatus() != UserStatus.ACTIVE || !Boolean.TRUE.equals(user.getIsActive())) {
            log.warn("User {} with status {} and isActive={} attempted token refresh.", user.getEmail(), user.getStatus(), user.getIsActive());
            throw new UserInactiveException("User account is " + user.getStatus().name().toLowerCase() + ". Authentication denied.");
        }

        log.info("Token successfully refreshed for user: {}", user.getEmail());

        return RefreshTokenResponse.builder()
                .idToken(fbResponse.getIdToken())
                .refreshToken(fbResponse.getRefreshToken())
                .tokenType(fbResponse.getTokenType() != null ? fbResponse.getTokenType() : "Bearer")
                .expiresIn(fbResponse.getExpiresIn() != null ? fbResponse.getExpiresIn() : 3600L)
                .firebaseUid(user.getFirebaseUid())
                .email(user.getEmail())
                .role(user.getRole())
                .displayName(user.getDisplayName())
                .status(user.getStatus())
                .build();
    }

    /**
     * Authenticates a user with email/phone and password.
     * Enforces conditional 2FA:
     * - If user is PATIENT and twoFactorEnabled == true:
     *     Dispatches OTP for re-authentication and returns twoFactorRequired = true (no auth tokens yet).
     * - If user is PATIENT and twoFactorEnabled == false (default):
     *     Direct login returning Firebase ID token and refresh token.
     * - For all other roles (SYSTEM_ADMIN, ADMIN, SPONSOR, SITE):
     *     Direct login returning Firebase ID token and refresh token (no 2FA).
     */
    public LoginResponse login(LoginRequest request) {
        return login(request, null);
    }

    @Transactional
    public LoginResponse login(LoginRequest request, String clientIp) {
        if (request == null) {
            throw new IllegalArgumentException("Login request must not be null.");
        }
        if (request.getPassword() == null || request.getPassword().isBlank()) {
            throw new IllegalArgumentException("Password must not be blank.");
        }

        String email = request.getEmail() != null && !request.getEmail().isBlank()
                ? request.getEmail().trim().toLowerCase() : null;
        String phone = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank()
                ? request.getPhoneNumber().trim() : null;
        String identifier = request.getIdentifier() != null && !request.getIdentifier().isBlank()
                ? request.getIdentifier().trim() : null;

        if (email == null && phone == null && identifier != null) {
            if (identifier.contains("@")) {
                email = identifier.toLowerCase();
            } else {
                phone = identifier;
            }
        }

        if (email == null && phone == null) {
            throw new IllegalArgumentException("Email, phone number, or identifier is required for login.");
        }

        Optional<UserEntity> userOpt = Optional.empty();
        if (email != null) {
            userOpt = userRepository.findByEmail(email);
        }
        if (userOpt.isEmpty() && phone != null) {
            userOpt = otpService.findUserByPhone(phone);
        }

        if (userOpt.isEmpty()) {
            log.warn("Login attempt for non-existent user: email={}, phone={}", email, phone);
            throw new InvalidTokenException("Invalid email/phone or password.");
        }

        UserEntity user = userOpt.get();

        if (user.getStatus() != UserStatus.ACTIVE || !Boolean.TRUE.equals(user.getIsActive())) {
            log.warn("User {} with status {} and isActive={} attempted login.", user.getEmail(), user.getStatus(), user.getIsActive());
            throw new UserInactiveException("User account is " + user.getStatus().name().toLowerCase() + ". Authentication denied.");
        }

        if (!com.hekma.identity.multitenancy.TenantPaths.isChainActive(user.getTenant(), tenantRepository)) {
            log.warn("User {} belongs to tenant {} whose organization chain is not active. Login denied.",
                    user.getId(), user.getTenant().getSlug());
            throw new TenantSuspendedException("Tenant organization is not active. Authentication denied.");
        }

        // Every password is validated by Firebase through this API. Phone-only accounts use their
        // synthetic auth email; legacy phone-only accounts without one must reset their password first.
        String authEmail = user.getAuthEmail() != null ? user.getAuthEmail() : user.getEmail();
        if (authEmail == null) {
            log.warn("User {} has no Firebase login email. A password reset is required before password login.", user.getId());
            throw new InvalidTokenException("Invalid email/phone or password.");
        }
        FirebaseSignInResponse fbSignIn = firebaseService.signInWithPassword(authEmail, request.getPassword());

        boolean isPatient = user.getRole() == Role.PATIENT;
        boolean twoFactorEnabled = Boolean.TRUE.equals(user.getTwoFactorEnabled());
        boolean twoFactorRequired = isPatient && twoFactorEnabled;

        if (twoFactorRequired) {
            log.info("Patient user {} has 2FA enabled. Initiating OTP challenge.", user.getId());
            VerificationMode mode = user.getVerificationMode() != null
                    ? user.getVerificationMode()
                    : (user.getPhoneNumber() != null ? VerificationMode.PHONE : VerificationMode.EMAIL);

            SendOtpRequest otpRequest = SendOtpRequest.builder()
                    .phoneNumber(user.getPhoneNumber())
                    .email(user.getEmail())
                    .verificationMode(mode)
                    .purpose(OtpPurpose.RE_AUTHENTICATION)
                    .build();

            SendOtpResponse otpResponse = otpService.sendOtp(otpRequest, clientIp);

            String destinationMsg = (mode == VerificationMode.PHONE)
                    ? "registered phone number"
                    : "registered email address";

            return LoginResponse.builder()
                    .twoFactorRequired(true)
                    .twoFactorEnabled(true)
                    .otpAttemptId(otpResponse.getAttemptId())
                    .otpExpiresInSeconds(otpResponse.getExpiresInSeconds())
                    .verificationMode(mode)
                    .userId(user.getId())
                    .firebaseUid(user.getFirebaseUid())
                    .email(user.getEmail())
                    .phoneNumber(user.getPhoneNumber())
                    .role(user.getRole())
                    .displayName(user.getDisplayName())
                    .status(user.getStatus())
                    .tenantId(user.getTenantId())
                    .tenantSlug(user.getTenant() != null ? user.getTenant().getSlug() : null)
                    .message("Two-factor authentication required. An OTP has been sent to your " + destinationMsg + " for verification.")
                    .build();
        }

        log.info("Direct login successful for user: {} with role: {}", user.getEmail(), user.getRole());
        return LoginResponse.builder()
                .twoFactorRequired(false)
                .twoFactorEnabled(twoFactorEnabled)
                .idToken(fbSignIn.getIdToken())
                .refreshToken(fbSignIn.getRefreshToken())
                .tokenType("Bearer")
                .expiresIn(fbSignIn.getExpiresIn())
                .userId(user.getId())
                .firebaseUid(user.getFirebaseUid())
                .email(user.getEmail())
                .phoneNumber(user.getPhoneNumber())
                .displayName(user.getDisplayName())
                .role(user.getRole())
                .status(user.getStatus())
                .phoneVerified(user.getPhoneVerified())
                .emailVerified(user.getEmailVerified())
                .tenantId(user.getTenantId())
                .tenantSlug(user.getTenant() != null ? user.getTenant().getSlug() : null)
                .message("Login successful.")
                .build();

    }


    /**
     * Initializes the default SYSTEM_ADMIN user on application startup if not already present.
     * Automatically generates a cryptographically secure random password so no default password
     * needs to be stored in configuration files. The System Admin can reset their password via Firebase.
     */
    @Transactional
    public void initializeSystemAdmin(String email, String displayName) {
        String normalizedEmail = email.trim().toLowerCase();

        boolean systemAdminExists = userRepository.existsByRole(Role.SYSTEM_ADMIN);
        if (systemAdminExists || userRepository.existsByEmail(normalizedEmail)) {
            log.info("System Admin user already exists. Skipping initialization.");
            return;
        }

        log.info("Initializing default System Admin with email: {}", normalizedEmail);

        // Check if user already exists in Firebase
        Optional<FirebaseUserDto> existingFbUser = firebaseService.getUserByEmail(normalizedEmail);
        String firebaseUid;
        if (existingFbUser.isPresent()) {
            firebaseUid = existingFbUser.get().getUid();
            firebaseService.assignRoleClaim(firebaseUid, Role.SYSTEM_ADMIN);
        } else {
            String randomPassword = generateSecureRandomPassword();
            FirebaseUserDto createdFb = firebaseService.createUser(normalizedEmail, randomPassword, displayName, Role.SYSTEM_ADMIN);
            firebaseUid = createdFb.getUid();
        }

        UserEntity adminEntity = UserEntity.builder()
                .firebaseUid(firebaseUid)
                .email(normalizedEmail)
                .authEmail(normalizedEmail)
                .role(Role.SYSTEM_ADMIN)
                .displayName(displayName)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .phoneVerified(false)
                .emailVerified(true)
                .twoFactorEnabled(false)
                .verificationMode(VerificationMode.EMAIL)
                .build();

        userRepository.save(adminEntity);
        log.info("Default System Admin initialized successfully with Firebase UID: {}. A random temporary password was generated. System Admin can use the password reset flow to set their password.", firebaseUid);
    }

    @Transactional
    public void initializePlatformAdmin(String email, String displayName) {
        String normalizedEmail = email.trim().toLowerCase();

        boolean adminExists = userRepository.existsByRole(Role.ADMIN);
        if (adminExists || userRepository.existsByEmail(normalizedEmail)) {
            log.info("Platform Admin user already exists. Skipping initialization.");
            return;
        }

        log.info("Initializing default Platform Admin with email: {}", normalizedEmail);

        Optional<FirebaseUserDto> existingFbUser = firebaseService.getUserByEmail(normalizedEmail);
        String firebaseUid;
        if (existingFbUser.isPresent()) {
            firebaseUid = existingFbUser.get().getUid();
            firebaseService.assignRoleClaim(firebaseUid, Role.ADMIN);
        } else {
            String randomPassword = generateSecureRandomPassword();
            FirebaseUserDto createdFb = firebaseService.createUser(normalizedEmail, randomPassword, displayName, Role.ADMIN);
            firebaseUid = createdFb.getUid();
        }

        UserEntity adminEntity = UserEntity.builder()
                .firebaseUid(firebaseUid)
                .email(normalizedEmail)
                .authEmail(normalizedEmail)
                .role(Role.ADMIN)
                .displayName(displayName)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .phoneVerified(false)
                .emailVerified(true)
                .twoFactorEnabled(false)
                .verificationMode(VerificationMode.EMAIL)
                .tenant(null)
                .build();

        userRepository.save(adminEntity);
        log.info("Default Platform Admin initialized successfully with Firebase UID: {}. A random temporary password was generated.", firebaseUid);
    }


    private RegisterResponse createUserWithRole(String email, String password, String displayName, Role role, String successMessage) {
        String normalizedEmail = email.trim().toLowerCase();

        if (userRepository.existsByEmail(normalizedEmail)) {
            throw new UserAlreadyExistsException("A user with email '" + normalizedEmail + "' is already registered in the system.");
        }

        Optional<FirebaseUserDto> existingFbUser = firebaseService.getUserByEmail(normalizedEmail);
        if (existingFbUser.isPresent()) {
            throw new UserAlreadyExistsException("A user with email '" + normalizedEmail + "' already exists in Firebase.");
        }

        FirebaseUserDto firebaseUser = firebaseService.createUser(normalizedEmail, password, displayName, role);

        try {
            UserEntity userEntity = UserEntity.builder()
                    .firebaseUid(firebaseUser.getUid())
                    .email(normalizedEmail)
                    .authEmail(normalizedEmail)
                    .role(role)
                    .displayName(displayName != null ? displayName.trim() : null)
                    .status(UserStatus.ACTIVE)
                    .isActive(true)
                    .isDeleted(false)
                    .phoneVerified(false)
                    .emailVerified(true)
                    .twoFactorEnabled(false)
                    .verificationMode(VerificationMode.EMAIL)
                    .build();

            userEntity = userRepository.save(userEntity);

            return RegisterResponse.builder()
                    .id(userEntity.getId())
                    .firebaseUid(userEntity.getFirebaseUid())
                    .email(userEntity.getEmail())
                    .role(userEntity.getRole())
                    .displayName(userEntity.getDisplayName())
                    .status(userEntity.getStatus())
                    .phoneVerified(userEntity.getPhoneVerified())
                    .emailVerified(userEntity.getEmailVerified())
                    .twoFactorEnabled(userEntity.getTwoFactorEnabled())
                    .verificationMode(userEntity.getVerificationMode())
                    .createdAt(userEntity.getCreatedAt())
                    .message(successMessage)
                    .build();
        } catch (Exception e) {
            log.error("Failed to persist user {} to database. Performing compensating rollback in Firebase: {}", normalizedEmail, e.getMessage());
            firebaseService.deleteUser(firebaseUser.getUid());
            throw e;
        }
    }

    /**
     * Generates a 20-character cryptographically strong password containing uppercase, lowercase,
     * digits, and special characters.
     */
    private String generateSecureRandomPassword() {
        String allChars = UPPERCASE + LOWERCASE + DIGITS + SYMBOLS;
        List<Character> chars = new ArrayList<>(20);

        // Guarantee at least one character from each set
        chars.add(UPPERCASE.charAt(SECURE_RANDOM.nextInt(UPPERCASE.length())));
        chars.add(LOWERCASE.charAt(SECURE_RANDOM.nextInt(LOWERCASE.length())));
        chars.add(DIGITS.charAt(SECURE_RANDOM.nextInt(DIGITS.length())));
        chars.add(SYMBOLS.charAt(SECURE_RANDOM.nextInt(SYMBOLS.length())));

        for (int i = 4; i < 20; i++) {
            chars.add(allChars.charAt(SECURE_RANDOM.nextInt(allChars.length())));
        }

        Collections.shuffle(chars, SECURE_RANDOM);

        StringBuilder sb = new StringBuilder(chars.size());
        for (char c : chars) {
            sb.append(c);
        }
        return sb.toString();
    }

    @Transactional
    public String forgotPassword(com.hekma.identity.dto.ForgotPasswordRequest request, String clientIp) {
        String id = request.getIdentifier() != null && !request.getIdentifier().isBlank()
                ? request.getIdentifier().trim()
                : (request.getEmail() != null && !request.getEmail().isBlank() ? request.getEmail().trim() : request.getPhoneNumber());

        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Identifier, email, or phone number is required.");
        }

        Optional<UserEntity> userOpt = id.contains("@")
                ? userRepository.findByEmail(id.toLowerCase())
                : userRepository.findByPhoneNumber(id);

        if (userOpt.isEmpty()) {
            log.warn("Password reset requested for an unknown identifier. No OTP generated.");
            return PASSWORD_RESET_DISPATCHED_MESSAGE;
        }

        UserEntity user = userOpt.get();
        boolean preferEmail = id.contains("@") || (request.getEmail() != null && !request.getEmail().isBlank());

        log.info("Dispatching password reset OTP for user: {} (preferEmail: {})", user.getEmail(), preferEmail);

        if (preferEmail && user.getEmail() != null && !user.getEmail().isBlank()) {
            otpService.sendOtp(SendOtpRequest.builder()
                    .email(user.getEmail())
                    .verificationMode(VerificationMode.EMAIL)
                    .purpose(OtpPurpose.PASSWORD_RESET)
                    .build(), clientIp);
        } else if (user.getPhoneNumber() != null && !user.getPhoneNumber().isBlank()) {
            otpService.sendOtp(SendOtpRequest.builder()
                    .phoneNumber(user.getPhoneNumber())
                    .verificationMode(VerificationMode.PHONE)
                    .purpose(OtpPurpose.PASSWORD_RESET)
                    .build(), clientIp);
        } else if (user.getEmail() != null && !user.getEmail().isBlank()) {
            otpService.sendOtp(SendOtpRequest.builder()
                    .email(user.getEmail())
                    .verificationMode(VerificationMode.EMAIL)
                    .purpose(OtpPurpose.PASSWORD_RESET)
                    .build(), clientIp);
        } else {
            log.warn("User {} has neither valid email nor phone number. OTP cannot be dispatched.", user.getId());
        }

        return PASSWORD_RESET_DISPATCHED_MESSAGE;
    }

    /**
     * Changes the authenticated user's password. The current password is validated by Firebase through
     * this API, the new password is stored in Firebase via the Admin SDK, every existing session is revoked,
     * and a fresh session is returned so the caller stays signed in.
     *
     * @param userId the authenticated caller (from the verified access token)
     * @param request current and new password
     * @return new ID and refresh tokens
     */
    public com.hekma.identity.dto.ChangePasswordResponse changePassword(java.util.UUID userId,
                                                                         com.hekma.identity.dto.ChangePasswordRequest request) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new com.hekma.identity.exception.UserNotFoundException("User not found with ID: " + userId));

        if (request.getNewPassword().equals(request.getCurrentPassword())) {
            throw new IllegalArgumentException("The new password must be different from the current password.");
        }

        String authEmail = user.getAuthEmail() != null ? user.getAuthEmail() : user.getEmail();
        if (authEmail == null) {
            throw new IllegalArgumentException("Password login is not set up for this account. Use the password reset flow first.");
        }

        try {
            firebaseService.signInWithPassword(authEmail, request.getCurrentPassword());
        } catch (InvalidTokenException e) {
            log.warn("Password change for user {} rejected: current password is incorrect.", userId);
            throw new InvalidTokenException("Current password is incorrect.");
        }

        firebaseService.updatePassword(user.getFirebaseUid(), request.getNewPassword());
        firebaseService.revokeRefreshTokens(user.getFirebaseUid());
        FirebaseSignInResponse session = firebaseService.signInWithPassword(authEmail, request.getNewPassword());
        log.info("Password changed for user {}; previous sessions revoked.", userId);

        return com.hekma.identity.dto.ChangePasswordResponse.builder()
                .idToken(session.getIdToken())
                .refreshToken(session.getRefreshToken())
                .tokenType("Bearer")
                .expiresIn(session.getExpiresIn())
                .message("Password changed successfully. Other sessions have been signed out.")
                .build();
    }

    public void resetPassword(com.hekma.identity.dto.ResetPasswordRequest request) {
        resetPassword(request, null);
    }

    /**
     * Completes a password reset. The submitted code must match the user's latest pending
     * PASSWORD_RESET OTP. Phone-only accounts without a Firebase login email receive a synthetic one
     * so that their password can be validated by Firebase from now on. All existing sessions are revoked.
     */
    @Transactional(noRollbackFor = {com.hekma.identity.exception.InvalidOtpException.class,
            com.hekma.identity.exception.OtpExpiredException.class,
            com.hekma.identity.exception.OtpVerificationLimitException.class})
    public void resetPassword(com.hekma.identity.dto.ResetPasswordRequest request, String clientIp) {
        String id = request.getIdentifier().trim();
        Optional<UserEntity> userOpt = id.contains("@")
                ? userRepository.findByEmail(id.toLowerCase())
                : userRepository.findByPhoneNumber(id);

        if (userOpt.isEmpty()) {
            // Uniform response for unknown accounts (no account enumeration).
            throw new com.hekma.identity.exception.InvalidOtpException("Invalid or expired verification code.");
        }

        UserEntity user = userOpt.get();
        otpService.verifyPasswordResetOtp(user, request.getOtpCode(), clientIp);

        if (user.getAuthEmail() == null) {
            String authEmail = AuthEmails.resolve(user.getEmail());
            firebaseService.updateAuthEmail(user.getFirebaseUid(), authEmail);
            user.setAuthEmail(authEmail);
            userRepository.save(user);
        }

        firebaseService.updatePassword(user.getFirebaseUid(), request.getNewPassword());
        firebaseService.revokeRefreshTokens(user.getFirebaseUid());
        log.info("Password successfully reset for user {}; existing sessions revoked.", user.getId());
    }
}
