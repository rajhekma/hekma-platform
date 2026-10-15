package com.hekma.ctms.dto;

import com.hekma.ctms.config.TraceIdFilter;
import org.slf4j.MDC;

import java.time.Instant;
import java.util.List;

public record ApiErrorResponse(
        int status,
        String error,
        String message,
        List<String> details,
        String timestamp,
        String traceId
) {
    public static ApiErrorResponse of(int status, String error, String message) {
        return new ApiErrorResponse(status, error, message, List.of(), Instant.now().toString(), MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY));
    }

    public static ApiErrorResponse of(int status, String error, String message, List<String> details) {
        return new ApiErrorResponse(status, error, message, details, Instant.now().toString(), MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY));
    }
}
