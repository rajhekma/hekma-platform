package com.hekma.appointment.dto;

import com.hekma.appointment.domain.AppointmentRequestEntity;
import com.hekma.appointment.domain.RequestStatus;
import com.hekma.appointment.domain.RequestType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Representation of an appointment or reactivation request")
public class AppointmentRequestDto {

    private UUID id;
    private String requestId;
    private UUID tenantId;
    private String tenantPath;

    @NotBlank(message = "fromKey is required")
    private String fromKey;

    @NotBlank(message = "fromType is required")
    private String fromType;

    @NotBlank(message = "toKey is required")
    private String toKey;

    @NotBlank(message = "toType is required")
    private String toType;

    private String refKey1;
    private String refType1;
    private String refKey2;
    private String refType2;
    private String refKey3;
    private String refType3;

    @NotNull(message = "type is required")
    private RequestType type;

    private Instant requestTimestamp;
    private String requestDescription;
    private RequestStatus requestStatus;
    private String requestResponse;
    private Instant requestUpdateTimestamp;

    public static AppointmentRequestDto fromEntity(AppointmentRequestEntity entity) {
        return AppointmentRequestDto.builder()
                .id(entity.getId())
                .requestId(entity.getId() != null ? entity.getId().toString() : null)
                .tenantId(entity.getTenantId())
                .tenantPath(entity.getTenantPath())
                .fromKey(entity.getFromKey())
                .fromType(entity.getFromType())
                .toKey(entity.getToKey())
                .toType(entity.getToType())
                .refKey1(entity.getRefKey1())
                .refType1(entity.getRefType1())
                .refKey2(entity.getRefKey2())
                .refType2(entity.getRefType2())
                .refKey3(entity.getRefKey3())
                .refType3(entity.getRefType3())
                .type(entity.getType())
                .requestTimestamp(entity.getRequestTimestamp())
                .requestDescription(entity.getRequestDescription())
                .requestStatus(entity.getRequestStatus())
                .requestResponse(entity.getRequestResponse())
                .requestUpdateTimestamp(entity.getRequestUpdateTimestamp())
                .build();
    }
}
