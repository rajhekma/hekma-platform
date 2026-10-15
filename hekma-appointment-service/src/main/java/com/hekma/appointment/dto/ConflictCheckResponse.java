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
@Schema(description = "Result of schedule conflict evaluation")
public class ConflictCheckResponse {

    @Schema(description = "Whether a conflict exists", example = "false")
    private boolean hasConflict;

    @Schema(description = "Human-readable conflict explanation", example = "No appointment conflicts found.")
    private String message;

    @Schema(description = "Identifier of the busy user if conflicting")
    private String conflictingUser;
}
