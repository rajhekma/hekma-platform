package com.hekma.identity.support;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.firebase.MockFirebaseService;
import com.hekma.identity.security.HekmaPrincipal;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;
import java.util.UUID;

/**
 * Test helpers for authenticated requests.
 */
public final class TestAuthentication {

    private TestAuthentication() {
    }

    /**
     * Places the principal into the security context (for standalone MockMvc controller tests).
     */
    public static HekmaPrincipal authenticate(HekmaPrincipal principal) {
        List<SimpleGrantedAuthority> granted = new java.util.ArrayList<>();
        granted.add(new SimpleGrantedAuthority("ROLE_" + principal.role().name()));
        principal.authorities().forEach(a -> granted.add(new SimpleGrantedAuthority(a.key())));
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(principal, null, granted));
        return principal;
    }

    public static HekmaPrincipal authenticate(UUID userId, Role role, UUID tenantId) {
        String path = tenantId != null ? "/" + tenantId + "/" : null;
        boolean staff = role == Role.SPONSOR || role == Role.SITE;
        return authenticate(staff
                ? new HekmaPrincipal(userId, "fb-" + userId, null, role, tenantId, path, Authority.OWNER_BUNDLE)
                : new HekmaPrincipal(userId, "fb-" + userId, null, role, tenantId, path));
    }

    public static void clear() {
        SecurityContextHolder.clearContext();
    }

    /**
     * Authorization header value with a mock Firebase ID token for the given user (full-context tests).
     */
    public static String bearer(UserEntity user) {
        return "Bearer " + MockFirebaseService.idTokenFor(user.getFirebaseUid());
    }
}
