package com.hekma.identity.security;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.VerifiedFirebaseToken;
import com.hekma.identity.multitenancy.TenantPaths;
import com.hekma.identity.repository.CustomRoleRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserAuthorityRepository;
import com.hekma.identity.repository.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.Optional;

/**
 * Authenticates requests carrying {@code Authorization: Bearer <Firebase ID token>}.
 * <ul>
 *   <li>No Bearer token: the request continues unauthenticated (only public endpoints will succeed).</li>
 *   <li>Invalid, expired or revoked token: 401.</li>
 *   <li>Unknown, deleted or non-active user, or a non-active tenant or ancestor tenant: 401/403.</li>
 * </ul>
 * The resulting {@link HekmaPrincipal} is built from the database record, never from token claims. Granted
 * authorities are {@code ROLE_<role>} plus the caller's authority keys (e.g. {@code patient:read}); platform
 * administrators receive every authority key.
 */
@Slf4j
public class FirebaseAuthenticationFilter extends OncePerRequestFilter {

    private static final String BEARER_PREFIX = "Bearer ";

    private final FirebaseService firebaseService;
    private final UserRepository userRepository;
    private final TenantRepository tenantRepository;
    private final UserAuthorityRepository userAuthorityRepository;
    private final CustomRoleRepository customRoleRepository;
    private final SecurityErrorWriter errorWriter;

    public FirebaseAuthenticationFilter(FirebaseService firebaseService, UserRepository userRepository,
                                        TenantRepository tenantRepository, UserAuthorityRepository userAuthorityRepository,
                                        CustomRoleRepository customRoleRepository,
                                        SecurityErrorWriter errorWriter) {
        this.firebaseService = firebaseService;
        this.userRepository = userRepository;
        this.tenantRepository = tenantRepository;
        this.userAuthorityRepository = userAuthorityRepository;
        this.customRoleRepository = customRoleRepository;
        this.errorWriter = errorWriter;
    }

    private static Set<Authority> toSet(Collection<Authority> granted) {
        if (granted == null || granted.isEmpty()) {
            return EnumSet.noneOf(Authority.class);
        }
        Set<Authority> set = EnumSet.noneOf(Authority.class);
        granted.stream().filter(Objects::nonNull).forEach(set::add);
        return set;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        if (path.equals("/graphiql") || path.startsWith("/graphiql/")) {
            return true;
        }
        String method = request.getMethod();
        if ("POST".equalsIgnoreCase(method)) {
            for (String publicPath : com.hekma.identity.config.SecurityConfig.PUBLIC_POST_ENDPOINTS) {
                if (path.equals(publicPath)) {
                    return true;
                }
            }
        }
        return false;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header == null || !header.startsWith(BEARER_PREFIX)) {
            filterChain.doFilter(request, response);
            return;
        }

        String idToken = header.substring(BEARER_PREFIX.length()).trim();
        VerifiedFirebaseToken token;
        try {
            token = firebaseService.verifyIdToken(idToken);
        } catch (InvalidTokenException e) {
            errorWriter.write(response, HttpStatus.UNAUTHORIZED, e.getMessage());
            return;
        }

        Optional<UserEntity> userOpt = userRepository.findWithTenantByFirebaseUid(token.firebaseUid());
        if (userOpt.isEmpty()) {
            log.warn("Verified token for Firebase UID {} has no matching active user record.", token.firebaseUid());
            errorWriter.write(response, HttpStatus.UNAUTHORIZED, "No registered account is associated with this token.");
            return;
        }

        UserEntity user = userOpt.get();
        if (user.getStatus() != UserStatus.ACTIVE || !Boolean.TRUE.equals(user.getIsActive())) {
            errorWriter.write(response, HttpStatus.FORBIDDEN, "User account is not active.");
            return;
        }

        TenantEntity tenant = user.getTenant();
        if (!TenantPaths.isChainActive(tenant, tenantRepository)) {
            errorWriter.write(response, HttpStatus.FORBIDDEN, "Tenant organization is not active.");
            return;
        }

        // Authorities are read on every request, so grants and revocations apply immediately.
        Set<String> customRoles = customRoleRepository.findRoleCodesByUserId(user.getId());
        Set<Authority> authorities = switch (user.getRole()) {
            case SYSTEM_ADMIN, ADMIN -> EnumSet.allOf(Authority.class);
            case SPONSOR, SITE -> {
                Set<Authority> direct = toSet(userAuthorityRepository.findAuthoritiesByUserId(user.getId()));
                Set<Authority> fromRoles = toSet(customRoleRepository.findAuthoritiesByUserId(user.getId()));
                EnumSet<Authority> combined = direct.isEmpty() ? EnumSet.noneOf(Authority.class) : EnumSet.copyOf(direct);
                combined.addAll(fromRoles);
                yield combined;
            }
            case PATIENT -> Set.of();
        };

        HekmaPrincipal principal = new HekmaPrincipal(
                user.getId(),
                user.getFirebaseUid(),
                user.getEmail(),
                user.getRole(),
                tenant != null ? tenant.getId() : null,
                tenant != null ? tenant.getPath() : null,
                authorities,
                customRoles);

        List<SimpleGrantedAuthority> granted = new ArrayList<>();
        granted.add(new SimpleGrantedAuthority("ROLE_" + user.getRole().name()));
        authorities.forEach(a -> granted.add(new SimpleGrantedAuthority(a.key())));

        UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(principal, null, granted);
        SecurityContextHolder.getContext().setAuthentication(authentication);

        filterChain.doFilter(request, response);
    }
}
