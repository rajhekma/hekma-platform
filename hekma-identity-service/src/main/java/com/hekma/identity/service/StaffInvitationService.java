package com.hekma.identity.service;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.StaffInvitationEntity;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.VerificationMode;
import com.hekma.identity.dto.UserResponse;
import com.hekma.identity.dto.iam.StaffAcceptInviteRequest;
import com.hekma.identity.dto.iam.StaffInviteRequest;
import com.hekma.identity.dto.iam.StaffInviteResponse;
import com.hekma.identity.exception.InvalidInvitationException;
import com.hekma.identity.exception.TenantNotFoundException;
import com.hekma.identity.exception.TenantSuspendedException;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseUserDto;
import com.hekma.identity.multitenancy.TenantPaths;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.repository.StaffInvitationRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.EnumSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/**
 * Staff (SPONSOR/SITE) invitations (RBAC Phase 3).
 * <ul>
 *   <li>The invitee's role always equals the target tenant's type (OD-3); the tenant must be in the inviter's subtree.</li>
 *   <li>Granted authorities never exceed the inviter's own (default bundle capped by the inviter's authorities).</li>
 *   <li>Tokens are random, single-use and valid for 72 hours; only their SHA-256 hash is stored.</li>
 * </ul>
 */
@Service
@Transactional
@Slf4j
public class StaffInvitationService {

    static final Duration INVITATION_VALIDITY = Duration.ofHours(72);
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final String ACCEPT_LINK = "https://app.hekma.com/invitations/accept?token=";

    private final StaffInvitationRepository invitationRepository;
    private final TenantRepository tenantRepository;
    private final UserRepository userRepository;
    private final FirebaseService firebaseService;
    private final AuthorityService authorityService;
    private final AuditService auditService;
    private final NotificationServiceClient notificationServiceClient;
    private final UserManagementService userManagementService;

    /**
     * Local development only: echo invitation links to the console (same switch as OTP echo).
     */
    private boolean consoleEcho = false;

    public StaffInvitationService(StaffInvitationRepository invitationRepository,
                                  TenantRepository tenantRepository,
                                  UserRepository userRepository,
                                  FirebaseService firebaseService,
                                  AuthorityService authorityService,
                                  AuditService auditService,
                                  NotificationServiceClient notificationServiceClient,
                                  UserManagementService userManagementService) {
        this.invitationRepository = invitationRepository;
        this.tenantRepository = tenantRepository;
        this.userRepository = userRepository;
        this.firebaseService = firebaseService;
        this.authorityService = authorityService;
        this.auditService = auditService;
        this.notificationServiceClient = notificationServiceClient;
        this.userManagementService = userManagementService;
    }

    @Value("${app.otp.console-echo:false}")
    void setConsoleEcho(boolean consoleEcho) {
        this.consoleEcho = consoleEcho;
    }

    /**
     * Invites a SPONSOR/SITE user into a tenant of the caller's subtree.
     */
    public StaffInviteResponse invite(StaffInviteRequest request, HekmaPrincipal caller) {
        TenantEntity tenant = tenantRepository.findById(request.getTenantId())
                .filter(caller::canSeeTenant)
                .orElseThrow(() -> new TenantNotFoundException("Tenant not found with ID: " + request.getTenantId()));
        Role role = tenant.getTenantType().staffRole();
        if (role == null) {
            throw new IllegalArgumentException("Staff cannot be invited into the default platform organization.");
        }
        if (!TenantPaths.isChainActive(tenant, tenantRepository)) {
            throw new TenantSuspendedException("Tenant organization '" + tenant.getName() + "' is not active.");
        }

        String email = request.getEmail().trim().toLowerCase();
        if (userRepository.existsByEmail(email) || firebaseService.getUserByEmail(email).isPresent()) {
            throw new UserAlreadyExistsException("A user with email '" + email + "' is already registered in the system.");
        }

        Set<Authority> authorities = resolveAuthorities(request.getAuthorities(), caller);

        String token = newToken();
        StaffInvitationEntity invitation = invitationRepository.save(StaffInvitationEntity.builder()
                .email(email)
                .role(role)
                .tenant(tenant)
                .tokenHash(hash(token))
                .authorities(AuthorityService.keys(authorities))
                .invitedBy(caller.userId())
                .expiresAt(Instant.now().plus(INVITATION_VALIDITY))
                .build());

        String link = ACCEPT_LINK + token;
        if (consoleEcho) {
            System.out.println(">>> [STAFF INVITATION] " + email + " -> " + link + " <<<");
        }
        try {
            notificationServiceClient.sendStaffInvitationEmail(email, null, tenant.getName(), link, invitation.getId());
        } catch (Exception e) {
            log.warn("Failed to dispatch staff invitation email to {}: {}", email, e.getMessage());
        }

        auditService.record(caller.userId(), AuditService.STAFF_INVITED, AuditService.TARGET_INVITATION,
                invitation.getId(), tenant.getId(), null, role + ":" + invitation.getAuthorities(), null);

        return StaffInviteResponse.builder()
                .invitationId(invitation.getId())
                .email(email)
                .role(role)
                .tenantId(tenant.getId())
                .tenantSlug(tenant.getSlug())
                .authorities(authorities.stream().map(Authority::key).sorted().toList())
                .expiresAt(invitation.getExpiresAt())
                .message("Invitation sent. It expires in 72 hours.")
                .build();
    }

    /**
     * Accepts an invitation (public): creates the Firebase account and the ACTIVE user, grants the invitation's
     * authorities and marks the invitation used. Firebase is rolled back if persistence fails.
     */
    public UserResponse accept(StaffAcceptInviteRequest request) {
        StaffInvitationEntity invitation = invitationRepository.findByTokenHash(hash(request.getToken().trim()))
                .orElseThrow(() -> new InvalidInvitationException("Invalid or expired invitation."));
        if (invitation.getAcceptedAt() != null || Instant.now().isAfter(invitation.getExpiresAt())) {
            throw new InvalidInvitationException("Invalid or expired invitation.");
        }
        TenantEntity tenant = invitation.getTenant();
        if (!TenantPaths.isChainActive(tenant, tenantRepository)) {
            throw new TenantSuspendedException("Tenant organization is not active. Invitation cannot be accepted.");
        }
        if (userRepository.existsByEmail(invitation.getEmail())) {
            throw new UserAlreadyExistsException("A user with this email is already registered in the system.");
        }
        String phone = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank() ? request.getPhoneNumber().trim() : null;
        if (phone != null && userRepository.existsByPhoneNumber(phone)) {
            throw new UserAlreadyExistsException("A user with phone number '" + phone + "' is already registered in the system.");
        }

        String displayName = request.getDisplayName() != null ? request.getDisplayName().trim() : null;
        FirebaseUserDto fbUser = firebaseService.createUser(invitation.getEmail(), request.getPassword(), displayName, invitation.getRole());
        try {
            firebaseService.assignClaims(fbUser.getUid(), invitation.getRole(), tenant.getId());
            UserEntity user = userRepository.save(UserEntity.builder()
                    .firebaseUid(fbUser.getUid())
                    .email(invitation.getEmail())
                    .authEmail(invitation.getEmail())
                    .role(invitation.getRole())
                    .displayName(displayName)
                    .phoneNumber(phone)
                    .status(UserStatus.ACTIVE)
                    .isActive(true)
                    .isDeleted(false)
                    .phoneVerified(false)
                    .emailVerified(true)
                    .twoFactorEnabled(false)
                    .verificationMode(VerificationMode.EMAIL)
                    .tenant(tenant)
                    .build());
            authorityService.grantInitial(user, AuthorityService.parseKeys(invitation.getAuthorities()), invitation.getInvitedBy());
            invitation.setAcceptedAt(Instant.now());
            invitationRepository.save(invitation);
            auditService.record(user.getId(), AuditService.STAFF_INVITATION_ACCEPTED, AuditService.TARGET_INVITATION,
                    invitation.getId(), tenant.getId(), null, user.getId().toString(), null);
            return userManagementService.toUserResponse(user, "Invitation accepted. You can now sign in.");
        } catch (RuntimeException e) {
            log.error("Failed to activate invited user {}. Performing compensating rollback in Firebase: {}", invitation.getEmail(), e.getMessage());
            firebaseService.deleteUser(fbUser.getUid());
            throw e;
        }
    }

    /**
     * Requested authorities must all be held by the inviter; without a request, the default bundle is capped by
     * the inviter's own authorities.
     */
    private static Set<Authority> resolveAuthorities(List<String> requested, HekmaPrincipal caller) {
        if (requested == null) {
            Set<Authority> defaults = EnumSet.noneOf(Authority.class);
            Authority.DEFAULT_INVITE_BUNDLE.stream().filter(caller::has).forEach(defaults::add);
            return defaults;
        }
        Set<Authority> wanted = parseStrict(requested);
        Set<Authority> notHeld = EnumSet.noneOf(Authority.class);
        wanted.stream().filter(a -> !caller.has(a)).forEach(notHeld::add);
        if (!notHeld.isEmpty()) {
            throw new UnauthorizedOperationException("You can only grant authorities you hold yourself: " + AuthorityService.keys(notHeld));
        }
        return wanted;
    }

    /**
     * Parses authority keys, rejecting unknown ones with 400.
     */
    public static Set<Authority> parseStrict(List<String> keys) {
        Set<Authority> set = EnumSet.noneOf(Authority.class);
        for (String key : keys) {
            set.add(Authority.fromKey(key == null ? "" : key.trim())
                    .orElseThrow(() -> new IllegalArgumentException("Unknown authority: " + key)));
        }
        return set;
    }

    static String newToken() {
        byte[] bytes = new byte[32];
        SECURE_RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    static String hash(String token) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
