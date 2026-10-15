package com.hekma.appointment.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.hekma.appointment.config.TraceIdFilter;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import org.slf4j.MDC;

import java.time.Instant;
import java.util.List;

@Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
@Schema(description = "Standard API error response payload")
public record ApiErrorResponse(
        @Schema(description = "HTTP status code", example = "400")
        int status,

        @Schema(description = "HTTP reason phrase", example = "Bad Request")
        String error,

        @Schema(description = "Human-readable error description", example = "Invalid appointment parameters")
        String message,

        @Schema(description = "Validation or processing details")
        List<String> details,

        @Schema(description = "Timestamp of the error occurrence")
        String timestamp,

        @Schema(description = "Correlation trace ID", example = "c6ac13b1-e96b-4a5f-8651-069c13e0fc64")
        String traceId
) {
    public static ApiErrorResponse of(int status, String error, String message) {
        return new ApiErrorResponse(status, error, message, List.of(), Instant.now().toString(), MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY));
    }

    public static ApiErrorResponse of(int status, String error, String message, List<String> details) {
        return new ApiErrorResponse(status, error, message, details, Instant.now().toString(), MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY));
    }
}
