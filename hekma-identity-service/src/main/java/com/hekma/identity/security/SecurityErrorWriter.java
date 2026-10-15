package com.hekma.identity.security;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

/**
 * Writes the standard {@code ApiErrorResponse} JSON body for errors raised in the security filter chain,
 * before requests reach the MVC layer and {@code GlobalExceptionHandler}.
 */
public class SecurityErrorWriter {

    public void write(HttpServletResponse response, HttpStatus status, String message) throws IOException {
        String traceId = org.slf4j.MDC.get(com.hekma.identity.config.TraceIdFilter.TRACE_ID_MDC_KEY);
        String traceJson = (traceId != null && !traceId.isBlank())
                ? ",\"traceId\":\"" + escape(traceId) + "\""
                : "";
        String body = "{\"status\":" + status.value()
                + ",\"error\":\"" + escape(status.getReasonPhrase())
                + "\",\"message\":\"" + escape(message)
                + "\",\"timestamp\":\"" + Instant.now() + "\""
                + traceJson + "}";
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(body);
    }

    private static String escape(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(value.length());
        for (char c : value.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        return sb.toString();
    }
}
