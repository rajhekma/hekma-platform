package com.hekma.identity.dto.tenant;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.domain.otp.VerificationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.UUID;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Result of tenant self-registration. Tenant and owner stay PENDING_VERIFICATION until the OTP is verified.")
public class RegisterTenantResponse {

    private UUID tenantId;
    private String tenantName;
    private String tenantSlug;
    private TenantType tenantType;
    private TenantStatus tenantStatus;

    private UUID userId;
    private String email;
    private String phoneNumber;
    private String displayName;
    private Role role;
    private UserStatus status;

    @Schema(description = "OTP attempt to pass to POST /api/v1/auth/otp/verify")
    private UUID otpAttemptId;
    private Long otpExpiresInSeconds;
    private VerificationMode verificationMode;

    private String message;
}
