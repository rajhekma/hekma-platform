package com.hekma.identity.multitenancy;

import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.security.HekmaPrincipal;
import com.hekma.identity.security.SecurityErrorWriter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Optional;
import java.util.UUID;

/**
 * Populates {@link TenantContext} for the current request from the authenticated principal.
 * Runs after {@code FirebaseAuthenticationFilter} inside the security filter chain.
 * <ul>
 *   <li>Tenant users (SPONSOR, SITE, PATIENT): the tenant is always the principal's own tenant.
 *       A different {@code X-Tenant-ID} header is rejected with 404.</li>
 *   <li>Platform administrators: {@code X-Tenant-ID} may select a target tenant; an unknown tenant is
 *       rejected with 404. Without the header, the request runs in platform (system bypass) context.</li>
 *   <li>Unauthenticated requests: no tenant context; the header is ignored.</li>
 * </ul>
 * An invalid tenant header never falls back to an unscoped context.
 */
@Slf4j
public class TenantFilter extends OncePerRequestFilter {

    public static final String TENANT_HEADER = "X-Tenant-ID";

    private final TenantRepository tenantRepository;
    private final SecurityErrorWriter errorWriter;

    public TenantFilter(TenantRepository tenantRepository, SecurityErrorWriter errorWriter) {
        this.tenantRepository = tenantRepository;
        this.errorWriter = errorWriter;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !(authentication.getPrincipal() instanceof HekmaPrincipal principal)) {
            filterChain.doFilter(request, response);
            return;
        }

        String tenantHeader = request.getHeader(TENANT_HEADER);
        boolean headerPresent = tenantHeader != null && !tenantHeader.isBlank();

        try {
            if (principal.isPlatformAdmin()) {
                if (headerPresent) {
                    Optional<UUID> tenantId = resolveTenantId(tenantHeader.trim());
                    if (tenantId.isEmpty()) {
                        errorWriter.write(response, HttpStatus.NOT_FOUND, "Tenant not found.");
                        return;
                    }
                    TenantContext.setTenantId(tenantId.get());
                } else {
                    TenantContext.setSystemBypass(true);
                }
            } else {
                if (headerPresent) {
                    Optional<UUID> requested = resolveTenantId(tenantHeader.trim());
                    if (requested.isEmpty() || !requested.get().equals(principal.tenantId())) {
                        log.warn("User {} requested tenant context outside of its own tenant.", principal.userId());
                        errorWriter.write(response, HttpStatus.NOT_FOUND, "Tenant not found.");
                        return;
                    }
                }
                TenantContext.setTenantId(principal.tenantId());
            }

            filterChain.doFilter(request, response);
        } finally {
            TenantContext.clear();
        }
    }

    private Optional<UUID> resolveTenantId(String identifier) {
        try {
            UUID id = UUID.fromString(identifier);
            return tenantRepository.existsById(id) ? Optional.of(id) : Optional.empty();
        } catch (IllegalArgumentException e) {
            return tenantRepository.findBySlug(identifier.toLowerCase()).map(TenantEntity::getId);
        }
    }
}
