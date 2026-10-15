package com.hekma.identity.service;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserAuthorityEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserNotFoundException;
import com.hekma.identity.repository.RoleAuthorityRepository;
import com.hekma.identity.repository.UserAuthorityRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.HekmaPrincipal;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collection;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Per-user authorities (RBAC Phase 3).
 * <ul>
 *   <li>Only SPONSOR/SITE users hold stored authorities; platform administrators hold all implicitly, patients none.</li>
 *   <li>Grant ≤ own: a caller can add or remove only authorities it holds itself.</li>
 *   <li>Scope: the target must be in the caller's tenant subtree (otherwise reported as not found).</li>
 *   <li>Nobody changes their own authorities.</li>
 * </ul>
 */
@Service
@Transactional
@Slf4j
public class AuthorityService {

    private final UserRepository userRepository;
    private final UserAuthorityRepository userAuthorityRepository;
    private final RoleAuthorityRepository roleAuthorityRepository;
    private final AuditService auditService;

    public AuthorityService(UserRepository userRepository,
                            UserAuthorityRepository userAuthorityRepository,
                            RoleAuthorityRepository roleAuthorityRepository,
                            AuditService auditService) {
        this.userRepository = userRepository;
        this.userAuthorityRepository = userAuthorityRepository;
        this.roleAuthorityRepository = roleAuthorityRepository;
        this.auditService = auditService;
    }

    /**
     * Effective authorities of a user as stored (SPONSOR/SITE/ADMIN), all (SYSTEM_ADMIN) or none (patients).
     */
    @Transactional(readOnly = true)
    public Set<Authority> effectiveAuthorities(UserEntity user) {
        return switch (user.getRole()) {
            case SYSTEM_ADMIN -> EnumSet.allOf(Authority.class);
            case ADMIN -> {
                Set<Authority> stored = toSet(userAuthorityRepository.findAuthoritiesByUserId(user.getId()));
                if (!stored.isEmpty()) {
                    yield stored;
                }
                Set<Authority> roleDefaults = roleAuthorityRepository.findAuthoritiesByRole(Role.ADMIN);
                yield (roleDefaults != null && !roleDefaults.isEmpty()) ? toSet(roleDefaults) : EnumSet.allOf(Authority.class);
            }
            case SPONSOR, SITE -> toSet(userAuthorityRepository.findAuthoritiesByUserId(user.getId()));
            case PATIENT -> EnumSet.noneOf(Authority.class);
        };
    }

    /**
     * Returns a user's authorities. Visible to the user itself, platform administrators, and SPONSOR/SITE users
     * holding {@code user:read} whose subtree contains the user.
     */
    @Transactional(readOnly = true)
    public Set<Authority> getAuthorities(UUID userId, HekmaPrincipal caller) {
        UserEntity target = userRepository.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("User not found with ID: " + userId));
        boolean self = target.getId().equals(caller.userId());
        if (!self && !(caller.has(Authority.USER_READ) && caller.canSeeTenant(target.getTenant()))) {
            throw new UserNotFoundException("User not found with ID: " + userId);
        }
        return effectiveAuthorities(target);
    }

    /**
     * Replaces a SPONSOR/SITE user's authorities with the requested set. Every added or removed authority must be
     * held by the caller (grant ≤ own). Audited with before/after values.
     */
    public Set<Authority> replaceAuthorities(UUID userId, Set<Authority> requested, String reason, HekmaPrincipal caller) {
        UserEntity target = userRepository.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("User not found with ID: " + userId));
        if (!caller.canSeeTenant(target.getTenant())) {
            throw new UserNotFoundException("User not found with ID: " + userId);
        }
        if (target.getId().equals(caller.userId())) {
            throw new UnauthorizedOperationException("Users cannot change their own authorities.");
        }
        if (target.getRole() != Role.SPONSOR && target.getRole() != Role.SITE && target.getRole() != Role.ADMIN) {
            throw new IllegalArgumentException("Authorities can only be assigned to ADMIN, SPONSOR or SITE users.");
        }

        Set<Authority> wanted = toSet(requested);
        List<UserAuthorityEntity> current = userAuthorityRepository.findByUser_Id(target.getId());
        Set<Authority> before = current.stream().map(UserAuthorityEntity::getAuthority).collect(Collectors.toCollection(() -> EnumSet.noneOf(Authority.class)));

        Set<Authority> added = EnumSet.copyOf(wanted.isEmpty() ? EnumSet.noneOf(Authority.class) : wanted);
        added.removeAll(before);
        Set<Authority> removed = before.isEmpty() ? EnumSet.noneOf(Authority.class) : EnumSet.copyOf(before);
        removed.removeAll(wanted);

        Set<Authority> notHeld = EnumSet.noneOf(Authority.class);
        added.stream().filter(a -> !caller.has(a)).forEach(notHeld::add);
        removed.stream().filter(a -> !caller.has(a)).forEach(notHeld::add);
        if (!notHeld.isEmpty()) {
            throw new UnauthorizedOperationException("You can only grant or revoke authorities you hold yourself: " + keys(notHeld));
        }

        current.stream().filter(ua -> removed.contains(ua.getAuthority())).forEach(userAuthorityRepository::delete);
        added.forEach(a -> userAuthorityRepository.save(UserAuthorityEntity.builder()
                .user(target).authority(a).grantedBy(caller.userId()).build()));

        if (!added.isEmpty() || !removed.isEmpty()) {
            auditService.record(caller.userId(), AuditService.AUTHORITIES_CHANGED, AuditService.TARGET_USER,
                    target.getId(), target.getTenantId(), keys(before), keys(wanted), reason);
        }
        log.info("Authorities of user {} changed by {}: +{} -{}", target.getId(), caller.userId(), keys(added), keys(removed));
        return wanted;
    }

    /**
     * Grants an initial authority set to a newly created SPONSOR/SITE user (registration owner, sub-tenant owner,
     * accepted invitation). {@code grantedBy} is null for self-service flows.
     */
    public void grantInitial(UserEntity user, Collection<Authority> authorities, UUID grantedBy) {
        if (authorities.isEmpty()) {
            return;
        }
        authorities.forEach(a -> userAuthorityRepository.save(UserAuthorityEntity.builder()
                .user(user).authority(a).grantedBy(grantedBy).build()));
        auditService.record(grantedBy, AuditService.AUTHORITIES_GRANTED, AuditService.TARGET_USER,
                user.getId(), user.getTenantId(), null, keys(authorities), "initial grant");
    }

    public static String keys(Collection<Authority> authorities) {
        return authorities.stream().map(Authority::key).sorted().collect(Collectors.joining(","));
    }

    public static Set<Authority> parseKeys(String csv) {
        Set<Authority> set = EnumSet.noneOf(Authority.class);
        if (csv == null || csv.isBlank()) {
            return set;
        }
        for (String key : csv.split(",")) {
            Authority.fromKey(key.trim()).ifPresent(set::add);
        }
        return set;
    }

    private static Set<Authority> toSet(Collection<Authority> authorities) {
        if (authorities == null || authorities.isEmpty()) {
            return EnumSet.noneOf(Authority.class);
        }
        Set<Authority> set = EnumSet.noneOf(Authority.class);
        authorities.stream().filter(Objects::nonNull).forEach(set::add);
        return set;
    }
}
