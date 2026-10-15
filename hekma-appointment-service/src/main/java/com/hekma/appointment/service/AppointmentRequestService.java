package com.hekma.appointment.service;

import com.hekma.appointment.domain.AppointmentRequestEntity;
import com.hekma.appointment.domain.RequestStatus;
import com.hekma.appointment.dto.AppointmentRequestDto;
import com.hekma.appointment.exception.ResourceNotFoundException;
import com.hekma.appointment.exception.UnauthorizedOperationException;
import com.hekma.appointment.repository.AppointmentRequestRepository;
import com.hekma.appointment.security.AppointmentPrincipal;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class AppointmentRequestService {

    private final AppointmentRequestRepository repository;

    @Transactional
    public AppointmentRequestDto createRequest(AppointmentRequestDto dto, AppointmentPrincipal principal) {
        log.info("Creating appointment request of type {} from {} to {}", dto.getType(), dto.getFromKey(), dto.getToKey());

        UUID tenantId = (principal != null && principal.tenantId() != null)
                ? principal.tenantId()
                : UUID.fromString("00000000-0000-0000-0000-000000000001");
        String tenantPath = (principal != null && principal.tenantPath() != null)
                ? principal.tenantPath()
                : "/" + tenantId + "/";

        AppointmentRequestEntity entity = AppointmentRequestEntity.builder()
                .tenantId(tenantId)
                .tenantPath(tenantPath)
                .fromKey(dto.getFromKey())
                .fromType(dto.getFromType())
                .toKey(dto.getToKey())
                .toType(dto.getToType())
                .refKey1(dto.getRefKey1())
                .refType1(dto.getRefType1())
                .refKey2(dto.getRefKey2())
                .refType2(dto.getRefType2())
                .refKey3(dto.getRefKey3())
                .refType3(dto.getRefType3())
                .type(dto.getType())
                .requestTimestamp(Instant.now())
                .requestDescription(dto.getRequestDescription())
                .requestStatus(RequestStatus.CREATED)
                .build();

        AppointmentRequestEntity saved = repository.save(entity);
        return AppointmentRequestDto.fromEntity(saved);
    }

    @Transactional(readOnly = true)
    public AppointmentRequestDto getRequestById(UUID id, AppointmentPrincipal principal) {
        AppointmentRequestEntity entity = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Appointment request not found with ID: " + id));

        if (principal != null && !principal.isPlatformAdmin() && !principal.isWithinSubtree(entity.getTenantPath())) {
            throw new UnauthorizedOperationException("Cannot access request outside your tenant scope.");
        }

        return AppointmentRequestDto.fromEntity(entity);
    }

    @Transactional(readOnly = true)
    public Page<AppointmentRequestDto> listRequests(RequestStatus status, Pageable pageable, AppointmentPrincipal principal) {
        if (principal != null && !principal.isPlatformAdmin() && principal.tenantPath() != null) {
            return repository.findAll((root, query, cb) -> {
                var p1 = cb.like(root.get("tenantPath"), principal.tenantPath() + "%");
                if (status != null) {
                    return cb.and(p1, cb.equal(root.get("requestStatus"), status));
                }
                return p1;
            }, pageable).map(AppointmentRequestDto::fromEntity);
        }

        if (status != null) {
            return repository.findAll((root, query, cb) -> cb.equal(root.get("requestStatus"), status), pageable)
                    .map(AppointmentRequestDto::fromEntity);
        }

        return repository.findAll(pageable).map(AppointmentRequestDto::fromEntity);
    }

    @Transactional
    public AppointmentRequestDto updateRequestStatus(UUID id, RequestStatus status, String responseMessage, AppointmentPrincipal principal) {
        AppointmentRequestEntity entity = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Appointment request not found with ID: " + id));

        if (principal != null && !principal.isPlatformAdmin() && !principal.isWithinSubtree(entity.getTenantPath())) {
            throw new UnauthorizedOperationException("Cannot update request outside your tenant scope.");
        }

        entity.setRequestStatus(status);
        entity.setRequestResponse(responseMessage);
        entity.setRequestUpdateTimestamp(Instant.now());

        AppointmentRequestEntity saved = repository.save(entity);
        log.info("Updated request {} status to {}", id, status);
        return AppointmentRequestDto.fromEntity(saved);
    }
}
