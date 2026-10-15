package com.hekma.identity.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;


@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request payload for updating user active/inactive status")
public class UpdateUserStatusRequest {

    @NotNull(message = "isActive is required (true to activate, false to deactivate)")
    @Schema(description = "Target active status (true = active, false = inactive)", example = "false", requiredMode = Schema.RequiredMode.REQUIRED)
    private Boolean isActive;

    @Schema(description = "Optional reason for status modification", example = "Account suspended due to compliance violation")
    private String reason;
}
