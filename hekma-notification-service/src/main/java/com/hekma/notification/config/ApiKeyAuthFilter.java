package com.hekma.notification.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Collections;
import java.util.List;

@Slf4j
public class ApiKeyAuthFilter extends OncePerRequestFilter {

    public static final String HEADER_API_KEY = "X-Hekma-Service-Key";
    private final String expectedApiKey;

    public ApiKeyAuthFilter(String expectedApiKey) {
        this.expectedApiKey = expectedApiKey;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {

        String path = request.getRequestURI();

        // Check if API key is provided
        String apiKey = request.getHeader(HEADER_API_KEY);

        if (apiKey != null && apiKey.equals(expectedApiKey)) {
            // Valid internal service key
            UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                    "internal-service",
                    null,
                    List.of(new SimpleGrantedAuthority("ROLE_INTERNAL_SERVICE"))
            );
            SecurityContextHolder.getContext().setAuthentication(authentication);
        } else if (path.startsWith("/api/v1/notifications")) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            String traceId = org.slf4j.MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY);
            String traceIdJson = (traceId != null && !traceId.isBlank()) ? ", \"traceId\": \"" + traceId + "\"" : "";
            response.getWriter().write("{\"error\": \"Unauthorized\", \"message\": \"Invalid or missing " + HEADER_API_KEY + " header\"" + traceIdJson + "}");
            return;
        }

        filterChain.doFilter(request, response);
    }
}
