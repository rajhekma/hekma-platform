package com.hekma.identity.service;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.exception.TenantNotFoundException;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.VerificationMode;
import com.hekma.identity.dto.patient.PatientAcceptInviteRequest;
import com.hekma.identity.dto.patient.PatientAssignRequest;
import com.hekma.identity.dto.patient.PatientInviteRequest;
import com.hekma.identity.dto.patient.PatientInviteResponse;
import com.hekma.identity.dto.patient.PatientResponse;
import com.hekma.identity.exception.InvalidInvitationException;
import com.hekma.identity.exception.TenantSuspendedException;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.exception.UserInactiveException;
import com.hekma.identity.exception.UserNotFoundException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseUserDto;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.multitenancy.TenantPaths;
import com.hekma.identity.security.AuthEmails;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Optional;
import java.util.List;
import java.util.UUID;

@Service
@Transactional
@Slf4j
public class PatientService {

    private final UserRepository userRepository;
    private final PatientDetailRepository patientDetailRepository;
    private final TenantRepository tenantRepository;
    private final FirebaseService firebaseService;
    private final NotificationServiceClient notificationServiceClient;
    private final AuditService auditService;

    static final java.time.Duration INVITATION_VALIDITY = java.time.Duration.ofHours(72);

    public PatientService(
            UserRepository userRepository,
            PatientDetailRepository patientDetailRepository,
            TenantRepository tenantRepository,
            FirebaseService firebaseService,
            NotificationServiceClient notificationServiceClient,
            AuditService auditService) {
        this.userRepository = userRepository;
        this.patientDetailRepository = patientDetailRepository;
        this.tenantRepository = tenantRepository;
        this.firebaseService = firebaseService;
        this.notificationServiceClient = notificationServiceClient;
        this.auditService = auditService;
    }

    /**
     * Rejects invitation codes that were already used or have expired. Legacy invitations without an expiry
     * (created before V7) remain usable until used.
     */
    static void requireUsableInvitation(PatientDetailEntity detail) {
        if (detail.getInvitationUsedAt() != null) {
            throw new InvalidInvitationException("This invitation has already been used.");
        }
        if (detail.getInvitationExpiresAt() != null && Instant.now().isAfter(detail.getInvitationExpiresAt())) {
            throw new InvalidInvitationException("This invitation has expired. Ask your study team for a new invitation.");
        }
    }

    /**
     * Invites a patient to a clinical study/trial.
     * Initiated by a SPONSOR or SITE user.
     * Stages a UserEntity (role=PATIENT, status=PENDING_VERIFICATION, tenant=inviter.tenant)
     * and maps patient_details.assigned_user_id to the inviter.
     */
    public PatientInviteResponse invitePatient(PatientInviteRequest request, UUID inviterId) {
        if (inviterId == null) {
            throw new UnauthorizedOperationException("An authenticated SPONSOR or SITE user is required to invite patients.");
        }

        UserEntity inviter = userRepository.findById(inviterId)
                .orElseThrow(() -> new UserNotFoundException("Inviting user not found with ID: " + inviterId));

        if (!Boolean.TRUE.equals(inviter.getIsActive()) || inviter.getStatus() != UserStatus.ACTIVE) {
            throw new UserInactiveException("Inviter account is inactive or suspended. Cannot invite patients.");
        }

        if (inviter.getRole() != Role.SPONSOR && inviter.getRole() != Role.SITE) {
            throw new UnauthorizedOperationException("Only SPONSOR or SITE users can create and invite patient profiles.");
        }

        TenantEntity inviterTenant = inviter.getTenant();
        if (inviterTenant == null) {
            throw new IllegalStateException("Inviter does not belong to any tenant organization.");
        }

        // Target tenant: the inviter's own tenant, or a sub-tenant within its subtree.
        TenantEntity tenant = inviterTenant;
        if (request.getTenantId() != null && !request.getTenantId().equals(inviterTenant.getId())) {
            tenant = tenantRepository.findById(request.getTenantId())
                    .filter(inviterTenant::containsInSubtree)
                    .orElseThrow(() -> new TenantNotFoundException("Tenant not found with ID: " + request.getTenantId()));
        }

        if (!TenantPaths.isChainActive(tenant, tenantRepository)) {
            throw new TenantSuspendedException("Tenant organization '" + tenant.getName() + "' is not active. Patient invitations denied.");
        }

        // Assignee: the inviter by default, otherwise a SPONSOR/SITE user in the inviter's subtree whose tenant is the
        // target tenant or one of its ancestors (so that the assignee can see the patient).
        UserEntity assignee = inviter;
        if (request.getAssignedUserId() != null && !request.getAssignedUserId().equals(inviter.getId())) {
            assignee = loadAssignableStaff(request.getAssignedUserId(), tenant, inviterTenant);
        }

        String normalizedEmail = request.getEmail().trim().toLowerCase();
        if (userRepository.existsByEmail(normalizedEmail)) {
            throw new UserAlreadyExistsException("A user with email '" + normalizedEmail + "' is already registered in the system.");
        }

        String normalizedPhone = request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank()
                ? request.getPhoneNumber().trim()
                : null;
        if (normalizedPhone != null && userRepository.existsByPhoneNumber(normalizedPhone)) {
            throw new UserAlreadyExistsException("A user with phone number '" + normalizedPhone + "' is already registered in the system.");
        }

        Optional<FirebaseUserDto> existingFb = firebaseService.getUserByEmail(normalizedEmail);
        if (existingFb.isPresent()) {
            throw new UserAlreadyExistsException("A user with email '" + normalizedEmail + "' already exists in Firebase.");
        }

        String invitationCode = "INV-" + UUID.randomUUID().toString().replace("-", "").substring(0, 10).toUpperCase();

        // The Firebase account is created on acceptance; until then the row carries a unique placeholder UID.
        UserEntity stagedUser = UserEntity.builder()
                .firebaseUid("pending-invite-" + UUID.randomUUID())
                .email(normalizedEmail)
                .role(Role.PATIENT)
                .tenant(tenant)
                .displayName(request.getFirstName().trim() + " " + request.getLastName().trim())
                .phoneNumber(normalizedPhone)
                .status(UserStatus.PENDING_VERIFICATION)
                .isActive(false)
                .isDeleted(false)
                .phoneVerified(false)
                .emailVerified(false)
                .twoFactorEnabled(false)
                .verificationMode(VerificationMode.EMAIL)
                .build();

        stagedUser = userRepository.save(stagedUser);

        PatientDetailEntity detail = PatientDetailEntity.builder()
                .user(stagedUser)
                .firstName(request.getFirstName().trim())
                .lastName(request.getLastName().trim())
                .phoneNumber(normalizedPhone)
                .invitationCode(invitationCode)
                .invitationExpiresAt(Instant.now().plus(INVITATION_VALIDITY))
                .assignedUser(assignee)
                .termsAccepted(false)
                .privacyPolicyAccepted(false)
                .healthDataConsentAccepted(false)
                .consentedAt(Instant.now())
                .build();

        patientDetailRepository.save(detail);
        auditService.record(inviter.getId(), AuditService.PATIENT_INVITED, AuditService.TARGET_USER,
                stagedUser.getId(), tenant.getId(), null, "assigned " + assignee.getId(), null);

        log.info("Patient profile staged for {} by inviter {} ({}) in tenant {}",
                normalizedEmail, inviter.getEmail(), inviter.getRole(), tenant.getSlug());

        String inviteLink = "https://app.hekma.com/register/patient?code=" + invitationCode;
        try {
            notificationServiceClient.sendPatientInvitationEmail(
                    normalizedEmail,
                    inviter.getDisplayName(),
                    tenant.getName(),
                    invitationCode,
                    inviteLink
            );
        } catch (Exception e) {
            log.warn("Failed to dispatch invitation email to {}: {}", normalizedEmail, e.getMessage());
        }

        return PatientInviteResponse.builder()
                .patientId(stagedUser.getId())
                .email(normalizedEmail)
                .invitationCode(invitationCode)
                .tenantId(tenant.getId())
                .tenantSlug(tenant.getSlug())
                .assignedUserId(assignee.getId())
                .message("Patient invited successfully. Invitation email dispatched.")
                .build();
    }

    /**
     * Accepts a clinical trial invitation, validates consents, sets password in Firebase,
     * assigns custom claims, and activates the patient profile.
     */
    public PatientResponse acceptInvite(PatientAcceptInviteRequest request) {
        if (!Boolean.TRUE.equals(request.getTermsAccepted()) ||
                !Boolean.TRUE.equals(request.getPrivacyPolicyAccepted()) ||
                !Boolean.TRUE.equals(request.getHealthDataConsentAccepted())) {
            throw new IllegalArgumentException("Terms, Privacy Policy, and Health Data Consents must all be accepted.");
        }

        String token = request.getInvitationToken().trim();
        PatientDetailEntity detail = patientDetailRepository.findByInvitationCode(token)
                .orElseThrow(() -> new InvalidInvitationException("Invalid or expired invitation code/token."));

        requireUsableInvitation(detail);
        UserEntity user = detail.getUser();
        if (user.getStatus() != UserStatus.PENDING_VERIFICATION) {
            throw new InvalidInvitationException("This patient invitation has already been processed or is not in pending status.");
        }

        if (user.getTenant() != null && user.getTenant().getStatus() == TenantStatus.SUSPENDED) {
            throw new TenantSuspendedException("Tenant organization is suspended. Cannot activate account.");
        }

        String authEmail = AuthEmails.resolve(user.getEmail());
        FirebaseUserDto fbUser = firebaseService.createUser(
                authEmail,
                request.getPassword(),
                user.getDisplayName(),
                Role.PATIENT
        );

        if (user.getTenant() != null) {
            firebaseService.assignClaims(fbUser.getUid(), Role.PATIENT, user.getTenantId());
        }

        user.setFirebaseUid(fbUser.getUid());
        user.setAuthEmail(authEmail);
        user.setStatus(UserStatus.ACTIVE);
        user.setIsActive(true);
        user.setEmailVerified(true);
        user = userRepository.save(user);

        detail.setTermsAccepted(true);
        detail.setPrivacyPolicyAccepted(true);
        detail.setHealthDataConsentAccepted(true);
        detail.setConsentedAt(Instant.now());
        detail.setInvitationUsedAt(Instant.now());
        detail = patientDetailRepository.save(detail);

        log.info("Patient {} successfully activated via invitation acceptance.", user.getEmail());

        try {
            notificationServiceClient.sendWelcomeEmail(user.getEmail(), user.getDisplayName());
            notificationServiceClient.sendWelcomeInApp(user.getId(), user.getDisplayName());
        } catch (Exception e) {
            log.warn("Failed to dispatch welcome notifications for user {}: {}", user.getId(), e.getMessage());
        }

        return toPatientResponse(detail, "Patient invitation accepted successfully. Account is now active.");
    }

    /**
     * Lists patients with role scoping:
     * - SPONSOR/SITE callers see patients of their tenant and all of its sub-tenants; supports assignedToMe=true.
     * - ADMIN/SYSTEM_ADMIN can view all patients across tenants or filter by specific tenantId.
     * - PATIENT callers see only their own profile.
     */
    @Transactional(readOnly = true)
    public Page<PatientResponse> listPatients(UUID callerId, Boolean assignedToMe, UUID filterTenantId, Pageable pageable) {
        if (callerId == null) {
            throw new UnauthorizedOperationException("An authenticated caller is required to list patients.");
        }

        UserEntity caller = userRepository.findById(callerId)
                .orElseThrow(() -> new UserNotFoundException("Caller user not found with ID: " + callerId));

        Page<PatientDetailEntity> details;
        if (caller.getRole() == Role.SPONSOR || caller.getRole() == Role.SITE) {
            if (caller.getTenant() == null) {
                throw new IllegalStateException("Staff user is not associated with a tenant organization.");
            }
            String subtree = caller.getTenant().getPath();

            if (Boolean.TRUE.equals(assignedToMe)) {
                details = patientDetailRepository.findByUser_Tenant_PathStartingWithAndAssignedUserId(subtree, caller.getId(), pageable);
            } else {
                details = patientDetailRepository.findByUser_Tenant_PathStartingWith(subtree, pageable);
            }
        } else if (caller.getRole() == Role.ADMIN || caller.getRole() == Role.SYSTEM_ADMIN) {
            if (filterTenantId != null) {
                details = patientDetailRepository.findByUser_Tenant_Id(filterTenantId, pageable);
            } else {
                details = patientDetailRepository.findAll(pageable);
            }
        } else {
            List<PatientDetailEntity> own = patientDetailRepository.findByUserId(caller.getId())
                    .map(List::of)
                    .orElse(List.of());
            details = new PageImpl<>(own, pageable, own.size());
        }

        return details.map(d -> toPatientResponse(d, null));
    }

    /**
     * Retrieves a patient profile by user UUID, scoped to the caller:
     * - PATIENT callers can only read their own profile.
     * - SPONSOR/SITE callers can only read patients of their tenant and its sub-tenants.
     * - ADMIN/SYSTEM_ADMIN can read any patient.
     * Patients outside the caller's scope are reported as not found.
     */
    @Transactional(readOnly = true)
    public PatientResponse getPatientById(UUID patientUserId, UUID callerId) {
        if (callerId == null) {
            throw new UnauthorizedOperationException("An authenticated caller is required to read patient profiles.");
        }

        PatientDetailEntity detail = patientDetailRepository.findByUserId(patientUserId)
                .orElseThrow(() -> new UserNotFoundException("Patient profile not found for user ID: " + patientUserId));

        UserEntity caller = userRepository.findById(callerId)
                .orElseThrow(() -> new UserNotFoundException("Caller user not found with ID: " + callerId));

        boolean allowed = switch (caller.getRole()) {
            case SYSTEM_ADMIN, ADMIN -> true;
            case SPONSOR, SITE -> caller.getTenant() != null && caller.getTenant().containsInSubtree(detail.getUser().getTenant());
            case PATIENT -> detail.getUser().getId().equals(caller.getId());
        };
        if (!allowed) {
            throw new UserNotFoundException("Patient profile not found for user ID: " + patientUserId);
        }

        return toPatientResponse(detail, null);
    }

    /**
     * Reassigns a patient to another SITE or SPONSOR investigator. The assignee's tenant must be the patient's tenant
     * or one of its ancestors; tenant users act only within their subtree.
     * Platform administrators can also assign an unassigned patient from default-tenant to a site coordinator.
     */
    public PatientResponse assignPatient(UUID patientUserId, PatientAssignRequest request, UUID operatorId) {
        if (operatorId == null) {
            throw new UnauthorizedOperationException("An authenticated operator is required to assign patients.");
        }

        UserEntity operator = userRepository.findById(operatorId)
                .orElseThrow(() -> new UserNotFoundException("Operator user not found with ID: " + operatorId));

        if (!Boolean.TRUE.equals(operator.getIsActive()) || operator.getStatus() != UserStatus.ACTIVE) {
            throw new UserInactiveException("Operator account is inactive or suspended.");
        }

        PatientDetailEntity detail = patientDetailRepository.findByUserId(patientUserId)
                .orElseThrow(() -> new UserNotFoundException("Patient profile not found for user ID: " + patientUserId));

        UserEntity targetAssignee = userRepository.findById(request.getAssignedUserId())
                .orElseThrow(() -> new UserNotFoundException("Target investigator not found with ID: " + request.getAssignedUserId()));

        if (!Boolean.TRUE.equals(targetAssignee.getIsActive()) || targetAssignee.getStatus() != UserStatus.ACTIVE) {
            throw new UserInactiveException("Target investigator account is inactive or suspended.");
        }

        if (targetAssignee.getRole() != Role.SPONSOR && targetAssignee.getRole() != Role.SITE) {
            throw new IllegalArgumentException("Patient can only be assigned to a SPONSOR or SITE investigator.");
        }

        TenantEntity patientTenant = detail.getUser().getTenant();
        if (operator.getRole() == Role.SPONSOR || operator.getRole() == Role.SITE) {
            TenantEntity operatorTenant = operator.getTenant();
            if (operatorTenant == null || !operatorTenant.containsInSubtree(patientTenant)) {
                throw new UserNotFoundException("Patient profile not found for user ID: " + patientUserId);
            }
            if (!operatorTenant.containsInSubtree(targetAssignee.getTenant())) {
                throw new UserNotFoundException("Target investigator not found with ID: " + request.getAssignedUserId());
            }
            requireAssigneeSeesPatient(targetAssignee, patientTenant);
        } else if (operator.getRole() == Role.ADMIN || operator.getRole() == Role.SYSTEM_ADMIN) {
            if (patientTenant != null && !Boolean.TRUE.equals(patientTenant.getDefaultTenant())) {
                requireAssigneeSeesPatient(targetAssignee, patientTenant);
            }
            // If patient was in default tenant, migrate patient's tenant to match assignee's tenant
            if (patientTenant != null && Boolean.TRUE.equals(patientTenant.getDefaultTenant())) {
                if (targetAssignee.getTenant() != null) {
                    detail.getUser().setTenant(targetAssignee.getTenant());
                    userRepository.save(detail.getUser());
                    firebaseService.assignClaims(detail.getUser().getFirebaseUid(), Role.PATIENT, targetAssignee.getTenantId());
                    log.info("Patient {} migrated from default-tenant to tenant {}",
                            detail.getUser().getEmail(), targetAssignee.getTenant().getSlug());
                }
            }
        } else {
            throw new UnauthorizedOperationException("Caller does not have permission to assign patients.");
        }

        UUID previousAssignee = detail.getAssignedUserId();
        detail.setAssignedUser(targetAssignee);
        PatientDetailEntity updated = patientDetailRepository.save(detail);
        auditService.record(operator.getId(), AuditService.PATIENT_ASSIGNED, AuditService.TARGET_USER,
                patientUserId, detail.getUser().getTenantId(), String.valueOf(previousAssignee), targetAssignee.getId().toString(), null);
        log.info("Patient {} reassigned to {} ({}) by operator {}",
                detail.getUser().getEmail(), targetAssignee.getEmail(), targetAssignee.getRole(), operator.getEmail());

        return toPatientResponse(updated, "Patient successfully assigned to " + targetAssignee.getDisplayName() + ".");
    }

    /**
     * Updates a patient's profile data (name, phone). Allowed for the patient itself, platform administrators, and
     * SPONSOR/SITE users holding {@code patient:update} whose subtree contains the patient's tenant.
     */
    public PatientResponse updatePatient(UUID patientUserId, com.hekma.identity.dto.patient.PatientUpdateRequest request,
                                         com.hekma.identity.security.HekmaPrincipal caller) {
        PatientDetailEntity detail = patientDetailRepository.findByUserId(patientUserId)
                .orElseThrow(() -> new UserNotFoundException("Patient profile not found for user ID: " + patientUserId));
        UserEntity patient = detail.getUser();
        boolean self = patient.getId().equals(caller.userId());
        boolean staff = caller.has(com.hekma.identity.domain.Authority.PATIENT_UPDATE) && caller.canSeeTenant(patient.getTenant());
        if (!self && !staff) {
            throw new UserNotFoundException("Patient profile not found for user ID: " + patientUserId);
        }

        if (request.getFirstName() != null && !request.getFirstName().isBlank()) {
            detail.setFirstName(request.getFirstName().trim());
        }
        if (request.getLastName() != null && !request.getLastName().isBlank()) {
            detail.setLastName(request.getLastName().trim());
        }
        if (request.getPhoneNumber() != null && !request.getPhoneNumber().isBlank()) {
            String phone = request.getPhoneNumber().trim();
            if (!phone.equals(patient.getPhoneNumber()) && userRepository.existsByPhoneNumber(phone)) {
                throw new UserAlreadyExistsException("A user with phone number '" + phone + "' is already registered in the system.");
            }
            detail.setPhoneNumber(phone);
            patient.setPhoneNumber(phone);
        }
        patient.setDisplayName(detail.getFirstName() + " " + detail.getLastName());
        userRepository.save(patient);
        PatientDetailEntity updated = patientDetailRepository.save(detail);
        log.info("Patient {} profile updated by {}", patientUserId, caller.userId());
        return toPatientResponse(updated, "Patient profile updated successfully.");
    }

    private UserEntity loadAssignableStaff(UUID userId, TenantEntity patientTenant, TenantEntity scope) {
        UserEntity assignee = userRepository.findById(userId)
                .filter(u -> u.getRole() == Role.SPONSOR || u.getRole() == Role.SITE)
                .filter(u -> scope.containsInSubtree(u.getTenant()))
                .orElseThrow(() -> new UserNotFoundException("Assignee not found with ID: " + userId));
        if (!Boolean.TRUE.equals(assignee.getIsActive()) || assignee.getStatus() != UserStatus.ACTIVE) {
            throw new UserInactiveException("Assignee account is inactive or suspended.");
        }
        requireAssigneeSeesPatient(assignee, patientTenant);
        return assignee;
    }

    /**
     * The assignee must be able to see the patient: its tenant is the patient's tenant or an ancestor of it.
     */
    private static void requireAssigneeSeesPatient(UserEntity assignee, TenantEntity patientTenant) {
        TenantEntity assigneeTenant = assignee.getTenant();
        if (assigneeTenant == null || !assigneeTenant.containsInSubtree(patientTenant)) {
            throw new IllegalArgumentException("The assignee must belong to the patient's tenant or one of its parent tenants.");
        }
    }

    public PatientResponse toPatientResponse(PatientDetailEntity detail, String message) {
        UserEntity user = detail.getUser();
        UserEntity assignedUser = detail.getAssignedUser();

        return PatientResponse.builder()
                .id(user.getId())
                .detailId(detail.getId())
                .email(user.getEmail())
                .displayName(user.getDisplayName())
                .firstName(detail.getFirstName())
                .lastName(detail.getLastName())
                .phoneNumber(detail.getPhoneNumber() != null ? detail.getPhoneNumber() : user.getPhoneNumber())
                .status(user.getStatus())
                .isActive(user.getIsActive())
                .tenantId(user.getTenantId())
                .tenantSlug(user.getTenant() != null ? user.getTenant().getSlug() : null)
                .assignedUserId(assignedUser != null ? assignedUser.getId() : null)
                .assignedUserName(assignedUser != null ? assignedUser.getDisplayName() : null)
                .invitationCode(detail.getInvitationCode())
                .termsAccepted(detail.isTermsAccepted())
                .privacyPolicyAccepted(detail.isPrivacyPolicyAccepted())
                .healthDataConsentAccepted(detail.isHealthDataConsentAccepted())
                .consentedAt(detail.getConsentedAt())
                .createdAt(user.getCreatedAt())
                .message(message)
                .build();
    }
}
