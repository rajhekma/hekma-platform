package com.hekma.identity.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.List;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Standard API error response")
public class ApiErrorResponse {

    @Schema(description = "HTTP status code", example = "400")
    private int status;

    @Schema(description = "Error title / reason phrase", example = "Bad Request")
    private String error;

    @Schema(description = "Detailed error message", example = "Validation failed for request")
    private String message;

    @Schema(description = "Timestamp when error occurred")
    private Instant timestamp;

    @Schema(description = "Optional list of detailed field validation errors")
    private List<String> details;

    @Schema(description = "Distributed trace correlation identifier", example = "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d")
    private String traceId;
}
