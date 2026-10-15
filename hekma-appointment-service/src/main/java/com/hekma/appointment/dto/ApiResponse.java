package com.hekma.appointment.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Standard operational response matching GraphQL and REST responses")
public class ApiResponse {

    @Schema(description = "HTTP status code", example = "200")
    private int status;

    @Schema(description = "Response type indicator", example = "SUCCESS")
    private String type;

    @Schema(description = "Message describing the operation result", example = "Appointment created successfully.")
    private String message;

    @Schema(description = "Associated record identifier or key attribute", example = "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d")
    private String attributes;

    public static ApiResponse success(String message, String attributes) {
        return new ApiResponse(200, "SUCCESS", message, attributes);
    }

    public static ApiResponse failed(int status, String message) {
        return new ApiResponse(status, "FAILED", message, null);
    }
}
