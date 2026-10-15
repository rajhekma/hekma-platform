package com.hekma.identity.dto.tenant;

import com.hekma.identity.domain.TenantStatus;
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
@Schema(description = "Payload for updating tenant operational status (SYSTEM_ADMIN only)")
public class TenantStatusUpdateRequest {

    @NotNull(message = "Tenant status is required (ACTIVE, SUSPENDED, INACTIVE)")
    @Schema(description = "Target tenant status", example = "SUSPENDED")
    private TenantStatus status;

    @Schema(description = "Reason for the status modification", example = "Regulatory compliance review")
    private String reason;
}
