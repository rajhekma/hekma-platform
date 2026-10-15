package com.hekma.identity.service;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.VerificationMode;
import com.hekma.identity.dto.tenant.SubTenantCreateRequest;
import com.hekma.identity.dto.tenant.TenantOwnerRequest;
import com.hekma.identity.dto.tenant.TenantResponse;
import com.hekma.identity.dto.tenant.TenantStatusUpdateRequest;
import com.hekma.identity.dto.tenant.TenantUpdateRequest;
import com.hekma.identity.exception.TenantNotFoundException;
import com.hekma.identity.exception.TenantSuspendedException;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseUserDto;
import com.hekma.identity.multitenancy.TenantPaths;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import jakarta.persistence.criteria.Predicate;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Tenant governance over a tenant hierarchy (RBAC Phase 2).
 * <ul>
 *   <li>SYSTEM_ADMIN / ADMIN see and manage every tenant.</li>
 *   <li>SPONSOR / SITE users see and manage their own tenant and its descendants (subtree); they can create
 *       sub-tenants of any type at any depth below it and change the status of strict descendants only.</li>
 *   <li>Top-level tenants are created only through tenant self-registration ({@code AuthService.registerTenant}).</li>
 *   <li>The default tenant (Hekma) cannot be suspended or receive sub-tenants.</li>
 * </ul>
 * Tenants outside the caller's scope are reported as not found.
 */
@Service
@Transactional
@Slf4j
public class TenantService {

    private final TenantRepository tenantRepository;
    private final UserRepository userRepository;
    private final FirebaseService firebaseService;
    private final AuthorityService authorityService;
    private final RoleAuthorityService roleAuthorityService;
    private final AuditService auditService;

    public TenantService(TenantRepository tenantRepository, UserRepository userRepository, FirebaseService firebaseService,
                         AuthorityService authorityService, RoleAuthorityService roleAuthorityService, AuditService auditService) {
        this.tenantRepository = tenantRepository;
        this.userRepository = userRepository;
        this.firebaseService = firebaseService;
        this.authorityService = authorityService;
        this.roleAuthorityService = roleAuthorityService;
        this.auditService = auditService;
    }

    /**
     * Lists tenants visible to the caller, optionally filtered by type and status.
     * Platform administrators see every tenant; tenant staff see their own subtree.
     */
    @Transactional(readOnly = true)
    public Page<TenantResponse> listTenants(TenantType type, TenantStatus status, Pageable pageable, HekmaPrincipal caller) {
        String prefix = caller.isPlatformAdmin() ? null : requireStaffPath(caller);
        Specification<TenantEntity> spec = (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();
            if (prefix != null && !prefix.isBlank()) {
                predicates.add(cb.like(root.get("path"), prefix + "%"));
            }
            if (type != null) {
                predicates.add(cb.equal(root.get("tenantType"), type));
            }
            if (status != null) {
                predicates.add(cb.equal(root.get("status"), status));
            }
            return predicates.isEmpty() ? cb.conjunction() : cb.and(predicates.toArray(new Predicate[0]));
        };
        return tenantRepository.findAll(spec, pageable)
                .map(tenant -> toTenantResponse(tenant, userRepository.countByTenant_Id(tenant.getId()), null));
    }

    /**
     * Retrieves tenant details by ID, scoped to the caller: platform administrators see every tenant,
     * tenant staff their subtree, patients only their own tenant.
     */
    @Transactional(readOnly = true)
    public TenantResponse getTenantById(UUID tenantId, HekmaPrincipal caller) {
        TenantEntity tenant = loadVisibleTenant(tenantId, caller);
        return toTenantResponse(tenant, userRepository.countByTenant_Id(tenant.getId()), null);
    }

    /**
     * Retrieves tenant details by URL slug (platform administrators).
     */
    @Transactional(readOnly = true)
    public TenantResponse getTenantBySlug(String slug) {
        TenantEntity tenant = tenantRepository.findBySlug(slug.trim().toLowerCase())
                .orElseThrow(() -> new TenantNotFoundException("Tenant not found with slug: " + slug));
        return toTenantResponse(tenant, userRepository.countByTenant_Id(tenant.getId()), null);
    }

    /**
     * Lists the direct sub-tenants of a tenant visible to the caller.
     */
    @Transactional(readOnly = true)
    public List<TenantResponse> getChildren(UUID tenantId, HekmaPrincipal caller) {
        TenantEntity parent = loadVisibleTenant(tenantId, caller);
        return tenantRepository.findByParent_IdOrderByNameAsc(parent.getId()).stream()
                .map(child -> toTenantResponse(child, userRepository.countByTenant_Id(child.getId()), null))
                .toList();
    }

    /**
     * Creates a sub-tenant (any type) under a parent tenant in the caller's scope, optionally with its first user.
     * The owner's role equals the sub-tenant's type. If the owner cannot be persisted, the Firebase account is
     * deleted again and the whole operation rolls back.
     */
    public TenantResponse createSubTenant(UUID parentId, SubTenantCreateRequest request, HekmaPrincipal caller) {
        TenantEntity parent = loadVisibleTenant(parentId, caller);

        if (Boolean.TRUE.equals(parent.getDefaultTenant())) {
            throw new UnauthorizedOperationException("Sub-tenants cannot be created under the default platform organization.");
        }
        if (!TenantPaths.isChainActive(parent, tenantRepository)) {
            throw new TenantSuspendedException("Parent tenant organization '" + parent.getName() + "' is not active.");
        }
        Role ownerRole = requireStaffType(request.getTenantType());

        String slug = request.getSlug().trim().toLowerCase();
        if (tenantRepository.existsBySlug(slug)) {
            throw new IllegalArgumentException("Tenant with slug '" + slug + "' already exists.");
        }

        TenantEntity tenant = tenantRepository.save(TenantEntity.builder()
                .parent(parent)
                .name(request.getName().trim())
                .slug(slug)
                .tenantType(request.getTenantType())
                .defaultTenant(false)
                .status(TenantStatus.ACTIVE)
                .subscriptionTier(request.getSubscriptionTier() != null ? request.getSubscriptionTier() : parent.getSubscriptionTier())
                .contactEmail(request.getContactEmail() != null ? request.getContactEmail().trim().toLowerCase() : null)
                .contactPhone(request.getContactPhone() != null ? request.getContactPhone().trim() : null)
                .settings(request.getSettings())
                .build());

        long members = 0;
        if (request.getOwner() != null) {
            createOwner(tenant, ownerRole, request.getOwner(), caller.userId());
            members = 1;
        }
        auditService.record(caller.userId(), AuditService.TENANT_CREATED, AuditService.TARGET_TENANT,
                tenant.getId(), tenant.getId(), null, tenant.getTenantType() + " under " + parent.getId(), null);

        log.info("Sub-tenant '{}' ({}, {}) created under '{}' by user {} ({}).",
                tenant.getSlug(), tenant.getTenantType(), tenant.getId(), parent.getSlug(), caller.userId(), caller.role());
        return toTenantResponse(tenant, members, "Sub-tenant organization created successfully.");
    }

    /**
     * Updates tenant status (ACTIVE, SUSPENDED, INACTIVE). Platform administrators may change any tenant;
     * tenant staff only strict descendants of their own tenant. The default tenant cannot be suspended or
     * deactivated. A non-active tenant blocks access for its whole subtree.
     */
    public TenantResponse updateTenantStatus(UUID tenantId, TenantStatusUpdateRequest request, HekmaPrincipal caller) {
        TenantEntity tenant = loadVisibleTenant(tenantId, caller);

        if (!caller.isPlatformAdmin() && tenant.getId().equals(caller.tenantId())) {
            throw new UnauthorizedOperationException("Tenant users cannot change the status of their own tenant organization.");
        }
        if (request.getStatus() == TenantStatus.PENDING_VERIFICATION) {
            throw new IllegalArgumentException("Status PENDING_VERIFICATION is set only by tenant self-registration.");
        }
        if (Boolean.TRUE.equals(tenant.getDefaultTenant()) &&
                (request.getStatus() == TenantStatus.SUSPENDED || request.getStatus() == TenantStatus.INACTIVE)) {
            throw new UnauthorizedOperationException("Default platform organization cannot be suspended or deactivated.");
        }

        TenantStatus before = tenant.getStatus();
        tenant.setStatus(request.getStatus());
        TenantEntity updated = tenantRepository.save(tenant);
        auditService.record(caller.userId(), AuditService.TENANT_STATUS_CHANGED, AuditService.TARGET_TENANT,
                updated.getId(), updated.getId(), String.valueOf(before), String.valueOf(request.getStatus()), request.getReason());
        log.info("Tenant '{}' ({}) status updated to {} by user {}. Reason: {}",
                updated.getName(), updated.getId(), request.getStatus(), caller.userId(), request.getReason());

        long memberCount = userRepository.countByTenant_Id(updated.getId());
        return toTenantResponse(updated, memberCount, "Tenant status updated to " + request.getStatus() + " successfully.");
    }

    /**
     * Updates tenant profile metadata. Platform administrators may update any tenant; tenant staff their subtree.
     */
    public TenantResponse updateTenant(UUID tenantId, TenantUpdateRequest request, HekmaPrincipal caller) {
        TenantEntity tenant = loadVisibleTenant(tenantId, caller);

        if (request.getName() != null && !request.getName().isBlank()) {
            tenant.setName(request.getName().trim());
        }
        if (request.getSubscriptionTier() != null && !request.getSubscriptionTier().isBlank()) {
            tenant.setSubscriptionTier(request.getSubscriptionTier().trim());
        }
        if (request.getContactEmail() != null) {
            tenant.setContactEmail(request.getContactEmail().trim().toLowerCase());
        }
        if (request.getContactPhone() != null) {
            tenant.setContactPhone(request.getContactPhone().trim());
        }
        if (request.getSettings() != null) {
            tenant.setSettings(request.getSettings());
        }

        TenantEntity updated = tenantRepository.save(tenant);
        auditService.record(caller.userId(), AuditService.TENANT_UPDATED, AuditService.TARGET_TENANT,
                updated.getId(), updated.getId(), null, null, null);
        log.info("Tenant '{}' ({}) metadata updated by user {}.", updated.getName(), updated.getId(), caller.userId());

        long memberCount = userRepository.countByTenant_Id(updated.getId());
        return toTenantResponse(updated, memberCount, "Tenant details updated successfully.");
    }

    /**
     * Loads a tenant and enforces the caller's visibility. Out-of-scope tenants are reported as not found.
     */
    private TenantEntity loadVisibleTenant(UUID tenantId, HekmaPrincipal caller) {
        TenantEntity tenant = tenantRepository.findById(tenantId)
                .orElseThrow(() -> new TenantNotFoundException("Tenant not found with ID: " + tenantId));
        boolean ownTenant = tenant.getId().equals(caller.tenantId());
        boolean visible = caller.isPlatformAdmin()
                || ownTenant
                || (caller.has(Authority.TENANT_READ) && caller.canSeeTenant(tenant));
        if (!visible) {
            throw new TenantNotFoundException("Tenant not found with ID: " + tenantId);
        }
        return tenant;
    }

    private String requireStaffPath(HekmaPrincipal caller) {
        if (!caller.isTenantStaff() || caller.tenantPath() == null) {
            throw new UnauthorizedOperationException("Only platform administrators and tenant users can list tenant organizations.");
        }
        return caller.tenantPath();
    }

    static Role requireStaffType(TenantType type) {
        Role role = type != null ? type.staffRole() : null;
        if (role == null) {
            throw new IllegalArgumentException("Tenant type must be SPONSOR or SITE.");
        }
        return role;
    }

    private void createOwner(TenantEntity tenant, Role role, TenantOwnerRequest owner, UUID grantedBy) {
        String email = owner.getEmail().trim().toLowerCase();
        String phone = owner.getPhoneNumber() != null && !owner.getPhoneNumber().isBlank() ? owner.getPhoneNumber().trim() : null;
        if (userRepository.existsByEmail(email) || firebaseService.getUserByEmail(email).isPresent()) {
            throw new UserAlreadyExistsException("A user with email '" + email + "' is already registered in the system.");
        }
        if (phone != null && userRepository.existsByPhoneNumber(phone)) {
            throw new UserAlreadyExistsException("A user with phone number '" + phone + "' is already registered in the system.");
        }

        FirebaseUserDto fbUser = firebaseService.createUser(email, owner.getTemporaryPassword(), owner.getDisplayName(), role);
        try {
            firebaseService.assignClaims(fbUser.getUid(), role, tenant.getId());
            UserEntity saved = userRepository.save(UserEntity.builder()
                    .firebaseUid(fbUser.getUid())
                    .email(email)
                    .authEmail(email)
                    .role(role)
                    .displayName(owner.getDisplayName() != null ? owner.getDisplayName().trim() : null)
                    .phoneNumber(phone)
                    .status(UserStatus.ACTIVE)
                    .isActive(true)
                    .isDeleted(false)
                    .phoneVerified(false)
                    .emailVerified(false)
                    .twoFactorEnabled(false)
                    .verificationMode(VerificationMode.EMAIL)
                    .tenant(tenant)
                    .build());
            authorityService.grantInitial(saved, roleAuthorityService.getRoleAuthorities(role), grantedBy);
        } catch (RuntimeException e) {
            log.error("Failed to persist owner {} of tenant {}. Performing compensating rollback in Firebase: {}",
                    email, tenant.getSlug(), e.getMessage());
            firebaseService.deleteUser(fbUser.getUid());
            throw e;
        }
    }

    TenantResponse toTenantResponse(TenantEntity tenant, long memberCount, String message) {
        return TenantResponse.builder()
                .id(tenant.getId())
                .name(tenant.getName())
                .slug(tenant.getSlug())
                .tenantType(tenant.getTenantType())
                .defaultTenant(tenant.getDefaultTenant())
                .status(tenant.getStatus())
                .subscriptionTier(tenant.getSubscriptionTier())
                .contactEmail(tenant.getContactEmail())
                .contactPhone(tenant.getContactPhone())
                .settings(tenant.getSettings())
                .parentTenantId(tenant.getParent() != null ? tenant.getParent().getId() : null)
                .path(tenant.getPath())
                .depth(tenant.getDepth())
                .memberCount(memberCount)
                .createdAt(tenant.getCreatedAt())
                .updatedAt(tenant.getUpdatedAt())
                .message(message)
                .build();
    }
}
