package com.hekma.identity.service;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.CustomRoleAuthorityEntity;
import com.hekma.identity.domain.CustomRoleEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.UserCustomRoleEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.dto.role.AssignCustomRolesRequest;
import com.hekma.identity.dto.role.CreateCustomRoleRequest;
import com.hekma.identity.dto.role.CustomRoleResponse;
import com.hekma.identity.dto.role.UpdateCustomRoleRequest;
import com.hekma.identity.dto.role.UserCustomRolesResponse;
import com.hekma.identity.exception.CustomRoleNotFoundException;
import com.hekma.identity.exception.TenantNotFoundException;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserNotFoundException;
import com.hekma.identity.repository.CustomRoleAuthorityRepository;
import com.hekma.identity.repository.CustomRoleRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserCustomRoleRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

@Service
@Transactional
@Slf4j
public class CustomRoleService {

    private final CustomRoleRepository customRoleRepository;
    private final CustomRoleAuthorityRepository customRoleAuthorityRepository;
    private final UserCustomRoleRepository userCustomRoleRepository;
    private final TenantRepository tenantRepository;
    private final UserRepository userRepository;
    private final AuditService auditService;

    public CustomRoleService(CustomRoleRepository customRoleRepository,
                             CustomRoleAuthorityRepository customRoleAuthorityRepository,
                             UserCustomRoleRepository userCustomRoleRepository,
                             TenantRepository tenantRepository,
                             UserRepository userRepository,
                             AuditService auditService) {
        this.customRoleRepository = customRoleRepository;
        this.customRoleAuthorityRepository = customRoleAuthorityRepository;
        this.userCustomRoleRepository = userCustomRoleRepository;
        this.tenantRepository = tenantRepository;
        this.userRepository = userRepository;
        this.auditService = auditService;
    }

    /**
     * Creates a new custom role within a tenant subtree, or globally if created by a platform admin.
     * Enforces Grant <= Own (caller can only bundle authorities they personally hold).
     */
    public CustomRoleResponse createCustomRole(CreateCustomRoleRequest request, HekmaPrincipal caller) {
        TenantEntity targetTenant = null;
        String tenantPath = null;

        if (caller.isPlatformAdmin()) {
            if (request.getTenantId() != null) {
                targetTenant = tenantRepository.findById(request.getTenantId())
                        .orElseThrow(() -> new TenantNotFoundException("Tenant not found with ID: " + request.getTenantId()));
                tenantPath = targetTenant.getPath();
            }
        } else {
            UUID tenantId = request.getTenantId() != null ? request.getTenantId() : caller.tenantId();
            if (tenantId == null) {
                throw new UnauthorizedOperationException("Tenant staff cannot create global custom roles.");
            }
            targetTenant = tenantRepository.findById(tenantId)
                    .orElseThrow(() -> new TenantNotFoundException("Tenant not found with ID: " + tenantId));
            if (caller.tenantPath() == null || targetTenant.getPath() == null || !targetTenant.getPath().startsWith(caller.tenantPath())) {
                throw new UnauthorizedOperationException("Cannot create custom role for tenant outside your subtree.");
            }
            tenantPath = targetTenant.getPath();
        }

        String code = request.getCode().trim().toUpperCase();
        if (targetTenant != null) {
            if (customRoleRepository.existsByTenant_IdAndCodeIgnoreCaseAndIsDeletedFalse(targetTenant.getId(), code)) {
                throw new IllegalArgumentException("A custom role with code '" + code + "' already exists in tenant '" + targetTenant.getName() + "'.");
            }
        } else {
            if (customRoleRepository.existsByTenantIsNullAndCodeIgnoreCaseAndIsDeletedFalse(code)) {
                throw new IllegalArgumentException("A global custom role with code '" + code + "' already exists.");
            }
        }

        Set<Authority> authorities = parseAuthorities(request.getAuthorities());
        if (authorities.isEmpty()) {
            throw new IllegalArgumentException("At least one valid authority must be specified for the custom role.");
        }
        validateCallerCanGrantAuthorities(authorities, caller);

        CustomRoleEntity entity = CustomRoleEntity.builder()
                .tenant(targetTenant)
                .tenantPath(tenantPath)
                .name(request.getName().trim())
                .code(code)
                .description(request.getDescription() != null ? request.getDescription().trim() : null)
                .isSystem(false)
                .isActive(true)
                .build();
        entity = customRoleRepository.save(entity);

        for (Authority authority : authorities) {
            customRoleAuthorityRepository.save(CustomRoleAuthorityEntity.builder()
                    .customRole(entity)
                    .authority(authority)
                    .build());
        }

        auditService.record(caller.userId(), AuditService.CUSTOM_ROLE_CREATED, AuditService.TARGET_CUSTOM_ROLE,
                entity.getId(), targetTenant != null ? targetTenant.getId() : null,
                null, entity.getCode(), "Created custom role " + entity.getName());

        return toResponse(entity);
    }

    /**
     * Updates an existing custom role. System roles are immutable.
     */
    public CustomRoleResponse updateCustomRole(UUID roleId, UpdateCustomRoleRequest request, HekmaPrincipal caller) {
        CustomRoleEntity role = customRoleRepository.findByIdAndIsDeletedFalse(roleId)
                .orElseThrow(() -> new CustomRoleNotFoundException("Custom role not found with ID: " + roleId));

        if (Boolean.TRUE.equals(role.getIsSystem())) {
            throw new UnauthorizedOperationException("System roles cannot be modified.");
        }

        if (!caller.isPlatformAdmin()) {
            if (role.getTenant() == null || caller.tenantPath() == null || role.getTenantPath() == null
                    || !role.getTenantPath().startsWith(caller.tenantPath())) {
                throw new UnauthorizedOperationException("Cannot modify custom role outside your tenant subtree.");
            }
        }

        String beforeValue = role.getName() + " [active=" + role.getIsActive() + "]";

        if (request.getName() != null && !request.getName().isBlank()) {
            role.setName(request.getName().trim());
        }
        if (request.getDescription() != null) {
            role.setDescription(request.getDescription().trim());
        }
        if (request.getIsActive() != null) {
            role.setIsActive(request.getIsActive());
        }

        if (request.getAuthorities() != null) {
            Set<Authority> newAuthorities = parseAuthorities(request.getAuthorities());
            if (newAuthorities.isEmpty()) {
                throw new IllegalArgumentException("A custom role must have at least one authority.");
            }
            validateCallerCanGrantAuthorities(newAuthorities, caller);

            customRoleAuthorityRepository.deleteByCustomRoleId(role.getId());
            for (Authority authority : newAuthorities) {
                customRoleAuthorityRepository.save(CustomRoleAuthorityEntity.builder()
                        .customRole(role)
                        .authority(authority)
                        .build());
            }
        }

        role = customRoleRepository.save(role);

        auditService.record(caller.userId(), AuditService.CUSTOM_ROLE_UPDATED, AuditService.TARGET_CUSTOM_ROLE,
                role.getId(), role.getTenant() != null ? role.getTenant().getId() : null,
                beforeValue, role.getName() + " [active=" + role.getIsActive() + "]", "Updated custom role");

        return toResponse(role);
    }

    /**
     * Soft deletes a custom role. Cannot delete if assigned to active users.
     */
    public void deleteCustomRole(UUID roleId, HekmaPrincipal caller) {
        CustomRoleEntity role = customRoleRepository.findByIdAndIsDeletedFalse(roleId)
                .orElseThrow(() -> new CustomRoleNotFoundException("Custom role not found with ID: " + roleId));

        if (Boolean.TRUE.equals(role.getIsSystem())) {
            throw new UnauthorizedOperationException("System roles cannot be deleted.");
        }

        if (!caller.isPlatformAdmin()) {
            if (role.getTenant() == null || caller.tenantPath() == null || role.getTenantPath() == null
                    || !role.getTenantPath().startsWith(caller.tenantPath())) {
                throw new UnauthorizedOperationException("Cannot delete custom role outside your tenant subtree.");
            }
        }

        long activeAssignedUsers = userCustomRoleRepository.countActiveUsersByCustomRoleId(role.getId());
        if (activeAssignedUsers > 0) {
            throw new IllegalStateException("Cannot delete custom role because it is currently assigned to " + activeAssignedUsers + " active user(s).");
        }

        role.setIsDeleted(true);
        customRoleRepository.save(role);

        auditService.record(caller.userId(), AuditService.CUSTOM_ROLE_DELETED, AuditService.TARGET_CUSTOM_ROLE,
                role.getId(), role.getTenant() != null ? role.getTenant().getId() : null,
                role.getCode(), "DELETED", "Soft deleted custom role " + role.getName());
    }

    /**
     * Retrieves a single custom role if visible to the caller.
     */
    @Transactional(readOnly = true)
    public CustomRoleResponse getCustomRole(UUID roleId, HekmaPrincipal caller) {
        CustomRoleEntity role = customRoleRepository.findByIdAndIsDeletedFalse(roleId)
                .orElseThrow(() -> new CustomRoleNotFoundException("Custom role not found with ID: " + roleId));

        if (!canCallerSeeRole(role, caller)) {
            throw new UnauthorizedOperationException("You do not have permission to view this custom role.");
        }

        return toResponse(role);
    }

    /**
     * Lists custom roles visible to caller (global roles + tenant subtree roles).
     */
    @Transactional(readOnly = true)
    public List<CustomRoleResponse> listCustomRoles(UUID tenantIdFilter, HekmaPrincipal caller) {
        List<CustomRoleEntity> roles;
        if (caller.isPlatformAdmin()) {
            if (tenantIdFilter != null) {
                roles = customRoleRepository.findByTenant_IdAndIsDeletedFalse(tenantIdFilter);
            } else {
                roles = customRoleRepository.findAllActiveRoles();
            }
        } else {
            if (tenantIdFilter != null) {
                TenantEntity filterTenant = tenantRepository.findById(tenantIdFilter)
                        .orElseThrow(() -> new TenantNotFoundException("Tenant not found with ID: " + tenantIdFilter));
                if (caller.tenantPath() == null || filterTenant.getPath() == null || !filterTenant.getPath().startsWith(caller.tenantPath())) {
                    throw new UnauthorizedOperationException("Cannot list roles for a tenant outside your subtree.");
                }
                roles = customRoleRepository.findByTenant_IdAndIsDeletedFalse(tenantIdFilter);
            } else {
                roles = customRoleRepository.findVisibleRoles(caller.tenantPath(), caller.tenantPath());
            }
        }
        return roles.stream().map(this::toResponse).toList();
    }

    /**
     * Assigns custom roles to a staff user. Enforces No Self-Elevation, Subtree Isolation, and Grant <= Own.
     */
    public UserCustomRolesResponse assignCustomRoles(UUID targetUserId, AssignCustomRolesRequest request, HekmaPrincipal caller) {
        UserEntity targetUser = userRepository.findById(targetUserId)
                .orElseThrow(() -> new UserNotFoundException("User not found with ID: " + targetUserId));

        if (Boolean.TRUE.equals(targetUser.getIsDeleted())) {
            throw new UserNotFoundException("User not found with ID: " + targetUserId);
        }

        // Invariant: No Self-Elevation
        if (targetUserId.equals(caller.userId())) {
            throw new UnauthorizedOperationException("You cannot assign or modify custom roles for yourself.");
        }

        // Invariant: Custom roles apply to operational staff only
        if (targetUser.getRole() == Role.PATIENT || targetUser.getRole() == Role.SYSTEM_ADMIN) {
            throw new UnauthorizedOperationException("Custom roles cannot be assigned to role: " + targetUser.getRole());
        }

        // Invariant: Subtree check on target user
        if (!caller.isPlatformAdmin()) {
            TenantEntity targetTenant = targetUser.getTenant();
            if (targetTenant == null || caller.tenantPath() == null || targetTenant.getPath() == null
                    || !targetTenant.getPath().startsWith(caller.tenantPath())) {
                throw new UnauthorizedOperationException("Cannot assign custom roles to users outside your tenant subtree.");
            }
        }

        UserEntity callerUser = userRepository.findById(caller.userId()).orElse(null);

        List<CustomRoleEntity> rolesToAssign = new ArrayList<>();
        Set<Authority> allAuthoritiesToGrant = EnumSet.noneOf(Authority.class);

        if (request.getRoleIds() != null && !request.getRoleIds().isEmpty()) {
            for (UUID roleId : request.getRoleIds()) {
                CustomRoleEntity role = customRoleRepository.findByIdAndIsDeletedFalse(roleId)
                        .orElseThrow(() -> new CustomRoleNotFoundException("Custom role not found with ID: " + roleId));

                if (!Boolean.TRUE.equals(role.getIsActive())) {
                    throw new IllegalArgumentException("Cannot assign inactive role: " + role.getName());
                }

                // Check role compatibility with target user's tenant
                if (role.getTenant() != null) {
                    TenantEntity targetTenant = targetUser.getTenant();
                    if (targetTenant == null || targetTenant.getPath() == null || role.getTenantPath() == null
                            || !targetTenant.getPath().startsWith(role.getTenantPath())) {
                        throw new UnauthorizedOperationException("Role '" + role.getName() + "' is not applicable to target user's tenant.");
                    }
                }

                Set<Authority> roleAuthorities = customRoleAuthorityRepository.findAuthoritiesByCustomRoleId(role.getId());
                if (roleAuthorities != null) {
                    roleAuthorities.stream().filter(Objects::nonNull).forEach(allAuthoritiesToGrant::add);
                }
                rolesToAssign.add(role);
            }
        }

        // Invariant: Grant <= Own
        validateCallerCanGrantAuthorities(allAuthoritiesToGrant, caller);

        List<UserCustomRoleEntity> currentAssignments = userCustomRoleRepository.findByUserId(targetUserId);
        String beforeCodes = currentAssignments.stream().map(a -> a.getCustomRole().getCode()).sorted().toList().toString();
        String afterCodes = rolesToAssign.stream().map(CustomRoleEntity::getCode).sorted().toList().toString();

        userCustomRoleRepository.deleteByUserId(targetUserId);
        userCustomRoleRepository.flush();

        for (CustomRoleEntity role : rolesToAssign) {
            userCustomRoleRepository.save(UserCustomRoleEntity.builder()
                    .user(targetUser)
                    .customRole(role)
                    .assignedBy(callerUser)
                    .build());
        }

        auditService.record(caller.userId(), AuditService.CUSTOM_ROLE_ASSIGNED, AuditService.TARGET_USER,
                targetUserId, targetUser.getTenant() != null ? targetUser.getTenant().getId() : null,
                beforeCodes, afterCodes, request.getReason());

        return getUserCustomRoles(targetUserId, caller);
    }

    /**
     * Retrieves the custom roles and inherited authorities assigned to a user.
     */
    @Transactional(readOnly = true)
    public UserCustomRolesResponse getUserCustomRoles(UUID targetUserId, HekmaPrincipal caller) {
        UserEntity targetUser = userRepository.findById(targetUserId)
                .orElseThrow(() -> new UserNotFoundException("User not found with ID: " + targetUserId));

        if (!caller.isPlatformAdmin() && !targetUserId.equals(caller.userId())) {
            TenantEntity targetTenant = targetUser.getTenant();
            if (targetTenant == null || caller.tenantPath() == null || targetTenant.getPath() == null
                    || !targetTenant.getPath().startsWith(caller.tenantPath())) {
                throw new UnauthorizedOperationException("Cannot view roles for users outside your tenant subtree.");
            }
        }

        List<UserCustomRoleEntity> assignments = userCustomRoleRepository.findByUserId(targetUserId);
        List<CustomRoleResponse> customRoles = assignments.stream()
                .map(UserCustomRoleEntity::getCustomRole)
                .filter(r -> !Boolean.TRUE.equals(r.getIsDeleted()))
                .map(this::toResponse)
                .toList();

        Set<Authority> authorities = customRoleRepository.findAuthoritiesByUserId(targetUserId);
        List<String> inheritedAuthorities = (authorities != null)
                ? authorities.stream().filter(Objects::nonNull).map(Authority::key).sorted().toList()
                : List.of();

        return UserCustomRolesResponse.builder()
                .userId(targetUser.getId())
                .userEmail(targetUser.getEmail())
                .customRoles(customRoles)
                .inheritedAuthorities(inheritedAuthorities)
                .build();
    }

    private boolean canCallerSeeRole(CustomRoleEntity role, HekmaPrincipal caller) {
        if (caller.isPlatformAdmin()) {
            return true;
        }
        if (role.getTenant() == null) {
            return true;
        }
        if (caller.tenantPath() != null && role.getTenantPath() != null) {
            return caller.tenantPath().startsWith(role.getTenantPath()) || role.getTenantPath().startsWith(caller.tenantPath());
        }
        return false;
    }

    private void validateCallerCanGrantAuthorities(Set<Authority> requestedAuthorities, HekmaPrincipal caller) {
        if (caller.isPlatformAdmin()) {
            return;
        }
        Set<Authority> callerAuthorities = caller.authorities();
        Set<Authority> unheld = EnumSet.copyOf(requestedAuthorities);
        unheld.removeAll(callerAuthorities);
        if (!unheld.isEmpty()) {
            throw new UnauthorizedOperationException("Cannot bundle or assign authorities you do not hold: " +
                    unheld.stream().map(Authority::key).sorted().toList());
        }
    }

    private Set<Authority> parseAuthorities(Set<String> authorityKeys) {
        if (authorityKeys == null || authorityKeys.isEmpty()) {
            return Set.of();
        }
        Set<Authority> set = EnumSet.noneOf(Authority.class);
        for (String key : authorityKeys) {
            Authority authority = Authority.fromKey(key)
                    .orElseThrow(() -> new IllegalArgumentException("Unknown authority key: '" + key + "'"));
            set.add(authority);
        }
        return set;
    }

    private CustomRoleResponse toResponse(CustomRoleEntity entity) {
        Set<Authority> authorities = customRoleAuthorityRepository.findAuthoritiesByCustomRoleId(entity.getId());
        List<String> authKeys = authorities != null
                ? authorities.stream().filter(Objects::nonNull).map(Authority::key).sorted().toList()
                : List.of();
        long assignedCount = userCustomRoleRepository.countActiveUsersByCustomRoleId(entity.getId());
        return CustomRoleResponse.builder()
                .id(entity.getId())
                .name(entity.getName())
                .code(entity.getCode())
                .description(entity.getDescription())
                .tenantId(entity.getTenant() != null ? entity.getTenant().getId() : null)
                .tenantPath(entity.getTenantPath())
                .isSystem(Boolean.TRUE.equals(entity.getIsSystem()))
                .isActive(Boolean.TRUE.equals(entity.getIsActive()))
                .authorities(authKeys)
                .totalAuthorities(authKeys.size())
                .assignedUserCount(assignedCount)
                .createdAt(entity.getCreatedAt())
                .updatedAt(entity.getUpdatedAt())
                .build();
    }
}
