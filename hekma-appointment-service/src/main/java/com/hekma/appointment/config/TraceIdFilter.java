package com.hekma.appointment.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * High-precedence servlet filter establishing distributed tracing context.
 * Ingests or generates a correlation trace ID, sets it in SLF4J MDC, appends
 * {@code X-Trace-Id} and {@code trace-id} response headers, and logs request lifecycle.
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    public static final String TRACE_ID_HEADER = "X-Trace-Id";
    public static final String TRACE_ID_HEADER_LOWER = "trace-id";
    public static final String REQUEST_ID_HEADER = "X-Request-Id";
    public static final String TRACE_ID_MDC_KEY = "traceId";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String traceId = resolveTraceId(request);
        MDC.put(TRACE_ID_MDC_KEY, traceId);
        response.setHeader(TRACE_ID_HEADER, traceId);
        response.setHeader(TRACE_ID_HEADER_LOWER, traceId);

        String method = request.getMethod();
        String uri = request.getRequestURI();
        String queryString = request.getQueryString();
        String fullPath = queryString != null ? uri + "?" + queryString : uri;

        long startTime = System.currentTimeMillis();
        boolean staticAsset = isStaticAsset(uri);

        if (!staticAsset) {
            log.info("HTTP API Request Started: {} {} | traceId={}", method, fullPath, traceId);
        }

        try {
            filterChain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            if (!staticAsset) {
                log.info("HTTP API Request Completed: {} {} | status={} | duration={}ms | traceId={}",
                        method, fullPath, response.getStatus(), duration, traceId);
            }
            MDC.remove(TRACE_ID_MDC_KEY);
        }
    }

    private boolean isStaticAsset(String uri) {
        return uri.startsWith("/swagger-ui") || uri.startsWith("/webjars") || uri.equals("/favicon.ico");
    }

    private String resolveTraceId(HttpServletRequest request) {
        String traceId = request.getHeader(TRACE_ID_HEADER);
        if (traceId == null || traceId.isBlank()) {
            traceId = request.getHeader(TRACE_ID_HEADER_LOWER);
        }
        if (traceId == null || traceId.isBlank()) {
            traceId = request.getHeader(REQUEST_ID_HEADER);
        }
        if (traceId == null || traceId.isBlank()) {
            traceId = UUID.randomUUID().toString();
        }
        return traceId.trim();
    }
}
