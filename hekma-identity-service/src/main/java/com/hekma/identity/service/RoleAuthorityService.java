package com.hekma.identity.service;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.RoleAuthorityEntity;
import com.hekma.identity.domain.UserAuthorityEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.dto.iam.AuthorityDefinitionResponse;
import com.hekma.identity.dto.iam.RoleAuthoritiesResponse;
import com.hekma.identity.repository.RoleAuthorityRepository;
import com.hekma.identity.repository.UserAuthorityRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Arrays;
import java.util.Collection;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Service managing platform authority catalogue metadata and default authorities per role (ADR-014).
 */
@Service
@Transactional
@Slf4j
public class RoleAuthorityService {

    private static final List<String> CONFIGURABLE_ROLES = List.of(Role.ADMIN.name(), Role.SPONSOR.name(), Role.SITE.name());

    private final RoleAuthorityRepository roleAuthorityRepository;
    private final UserAuthorityRepository userAuthorityRepository;
    private final UserRepository userRepository;
    private final AuditService auditService;

    public RoleAuthorityService(RoleAuthorityRepository roleAuthorityRepository,
                                UserAuthorityRepository userAuthorityRepository,
                                UserRepository userRepository,
                                AuditService auditService) {
        this.roleAuthorityRepository = roleAuthorityRepository;
        this.userAuthorityRepository = userAuthorityRepository;
        this.userRepository = userRepository;
        this.auditService = auditService;
    }

    /**
     * Returns the complete dictionary of all platform authorities with metadata and groupings.
     */
    @Transactional(readOnly = true)
    public List<AuthorityDefinitionResponse> getAuthorityCatalogue() {
        return Arrays.stream(Authority.values())
                .map(a -> AuthorityDefinitionResponse.builder()
                        .key(a.key())
                        .name(a.displayName())
                        .category(a.category())
                        .description(a.description())
                        .allowedRoles(CONFIGURABLE_ROLES)
                        .build())
                .toList();
    }

    /**
     * Resolves default authorities configured for a given role.
     */
    @Transactional(readOnly = true)
    public Set<Authority> getRoleAuthorities(Role role) {
        if (role == Role.SYSTEM_ADMIN) {
            return EnumSet.allOf(Authority.class);
        }
        if (role == Role.PATIENT) {
            return EnumSet.noneOf(Authority.class);
        }

        Set<Authority> configured = roleAuthorityRepository.findAuthoritiesByRole(role);
        if (configured != null && !configured.isEmpty()) {
            Set<Authority> valid = configured.stream()
                    .filter(Objects::nonNull)
                    .collect(Collectors.toCollection(() -> EnumSet.noneOf(Authority.class)));
            if (!valid.isEmpty()) {
                return valid;
            }
        }

        // Baseline fallbacks if table not yet populated
        return switch (role) {
            case ADMIN, SPONSOR, SITE -> EnumSet.allOf(Authority.class);
            default -> EnumSet.noneOf(Authority.class);
        };
    }

    /**
     * Returns a structured DTO of default authorities for a specific role.
     */
    @Transactional(readOnly = true)
    public RoleAuthoritiesResponse getRoleAuthoritiesResponse(Role role) {
        validateConfigurableRole(role);
        Set<Authority> authorities = getRoleAuthorities(role);
        return toRoleAuthoritiesResponse(role, authorities);
    }

    /**
     * Returns default authorities for all configurable roles (ADMIN, SPONSOR, SITE).
     */
    @Transactional(readOnly = true)
    public List<RoleAuthoritiesResponse> getAllRoleAuthorities() {
        return List.of(
                getRoleAuthoritiesResponse(Role.ADMIN),
                getRoleAuthoritiesResponse(Role.SPONSOR),
                getRoleAuthoritiesResponse(Role.SITE)
        );
    }

    /**
     * Updates default authorities for a configurable role with optional cascade to existing users.
     *
     * @param role target role (ADMIN, SPONSOR, SITE)
     * @param wanted requested authorities
     * @param applyToExistingUsers if true, updates existing users in identity_user_authorities
     * @param reason optional audit note
     * @param caller acting operator
     */
    public RoleAuthoritiesResponse updateRoleAuthorities(Role role,
                                                        Set<Authority> wanted,
                                                        boolean applyToExistingUsers,
                                                        String reason,
                                                        HekmaPrincipal caller) {
        validateConfigurableRole(role);

        Set<Authority> before = getRoleAuthorities(role);
        Set<Authority> targetSet = wanted != null && !wanted.isEmpty() ? EnumSet.copyOf(wanted) : EnumSet.noneOf(Authority.class);

        // Update role template using differential add/remove to prevent unique constraint violation
        List<RoleAuthorityEntity> currentRoleAuthorities = roleAuthorityRepository.findByRole(role);
        Set<Authority> existingRoleAuthorities = currentRoleAuthorities.stream()
                .map(RoleAuthorityEntity::getAuthority)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Set<Authority> roleAuthoritiesToAdd = EnumSet.noneOf(Authority.class);
        targetSet.stream().filter(a -> !existingRoleAuthorities.contains(a)).forEach(roleAuthoritiesToAdd::add);

        Set<Authority> roleAuthoritiesToRemove = EnumSet.noneOf(Authority.class);
        existingRoleAuthorities.stream().filter(a -> !targetSet.contains(a)).forEach(roleAuthoritiesToRemove::add);

        currentRoleAuthorities.stream()
                .filter(ra -> ra.getAuthority() == null || roleAuthoritiesToRemove.contains(ra.getAuthority()))
                .forEach(roleAuthorityRepository::delete);

        roleAuthoritiesToAdd.forEach(a -> roleAuthorityRepository.save(RoleAuthorityEntity.builder()
                .role(role)
                .authority(a)
                .build()));

        // Cascade to existing active users if requested
        int usersUpdated = 0;
        if (applyToExistingUsers) {
            List<UserEntity> existingUsers = userRepository.findByRoleOrderByCreatedAtDesc(role);
            for (UserEntity user : existingUsers) {
                List<UserAuthorityEntity> currentUas = userAuthorityRepository.findByUser_Id(user.getId());
                Set<Authority> currentSet = currentUas.stream()
                        .map(UserAuthorityEntity::getAuthority)
                        .filter(Objects::nonNull)
                        .collect(Collectors.toSet());

                // Remove authorities not in new set (or stale/null entries)
                currentUas.stream()
                        .filter(ua -> ua.getAuthority() == null || !targetSet.contains(ua.getAuthority()))
                        .forEach(userAuthorityRepository::delete);

                // Add newly assigned authorities
                targetSet.stream()
                        .filter(a -> !currentSet.contains(a))
                        .forEach(a -> userAuthorityRepository.save(UserAuthorityEntity.builder()
                                .user(user)
                                .authority(a)
                                .grantedBy(caller != null ? caller.userId() : null)
                                .build()));
                usersUpdated++;
            }
        }

        // Record privileged audit entry
        String auditReason = (reason != null && !reason.isBlank() ? reason + " | " : "")
                + "applyToExistingUsers=" + applyToExistingUsers + ", usersUpdated=" + usersUpdated;

        auditService.record(
                caller != null ? caller.userId() : null,
                AuditService.ROLE_AUTHORITIES_CHANGED,
                AuditService.TARGET_ROLE,
                null,
                null,
                AuthorityService.keys(before),
                AuthorityService.keys(targetSet),
                auditReason
        );

        log.info("Role authorities for {} updated by {}. Cascade: {}, affected users: {}",
                role, caller != null ? caller.userId() : "SYSTEM", applyToExistingUsers, usersUpdated);

        return toRoleAuthoritiesResponse(role, targetSet);
    }

    private void validateConfigurableRole(Role role) {
        if (role == null) {
            throw new IllegalArgumentException("Role cannot be null.");
        }
        if (role == Role.SYSTEM_ADMIN) {
            throw new IllegalArgumentException("SYSTEM_ADMIN authorities are immutable and cannot be modified.");
        }
        if (role == Role.PATIENT) {
            throw new IllegalArgumentException("PATIENT role cannot be assigned administrative authorities.");
        }
        if (role != Role.ADMIN && role != Role.SPONSOR && role != Role.SITE) {
            throw new IllegalArgumentException("Role " + role + " is not configurable.");
        }
    }

    private static RoleAuthoritiesResponse toRoleAuthoritiesResponse(Role role, Collection<Authority> authorities) {
        List<String> sortedKeys = authorities.stream()
                .map(Authority::key)
                .sorted()
                .toList();

        return RoleAuthoritiesResponse.builder()
                .role(role)
                .authorities(sortedKeys)
                .totalAuthorities(sortedKeys.size())
                .build();
    }
}
