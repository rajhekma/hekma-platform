package com.hekma.ctms.security;

import com.hekma.ctms.security.client.IdentityServiceClient;
import com.hekma.ctms.security.client.TokenIntrospectResponse;
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
import java.util.List;

@Slf4j
public class IntrospectionAuthenticationFilter extends OncePerRequestFilter {

    private static final String BEARER_PREFIX = "Bearer ";

    private final IdentityServiceClient identityServiceClient;
    private final SecurityErrorWriter errorWriter;

    public IntrospectionAuthenticationFilter(IdentityServiceClient identityServiceClient, SecurityErrorWriter errorWriter) {
        this.identityServiceClient = identityServiceClient;
        this.errorWriter = errorWriter;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path.equals("/graphiql") || path.startsWith("/graphiql/");
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

        String token = header.substring(BEARER_PREFIX.length()).trim();
        TokenIntrospectResponse introspect = identityServiceClient.introspect(token);

        if (!introspect.active()) {
            errorWriter.write(response, HttpStatus.UNAUTHORIZED, "Invalid, expired, or inactive access token.");
            return;
        }

        CtmsPrincipal principal = new CtmsPrincipal(
                introspect.userId(),
                introspect.email(),
                introspect.role(),
                introspect.tenantId(),
                introspect.tenantPath(),
                introspect.authorities(),
                introspect.customRoles()
        );

        List<SimpleGrantedAuthority> grantedAuthorities = new ArrayList<>();
        if (introspect.role() != null) {
            grantedAuthorities.add(new SimpleGrantedAuthority("ROLE_" + introspect.role()));
        }
        if (introspect.authorities() != null) {
            for (String auth : introspect.authorities()) {
                grantedAuthorities.add(new SimpleGrantedAuthority(auth));
            }
        }

        UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                principal,
                null,
                grantedAuthorities
        );

        SecurityContextHolder.getContext().setAuthentication(authentication);
        try {
            filterChain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
