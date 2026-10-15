package com.hekma.appointment.repository;

import com.hekma.appointment.domain.AppointmentRequestEntity;
import com.hekma.appointment.domain.RequestStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface AppointmentRequestRepository extends JpaRepository<AppointmentRequestEntity, UUID>, JpaSpecificationExecutor<AppointmentRequestEntity> {

    List<AppointmentRequestEntity> findByFromKeyOrderByRequestTimestampDesc(String fromKey);

    List<AppointmentRequestEntity> findByToKeyOrderByRequestTimestampDesc(String toKey);

    List<AppointmentRequestEntity> findByTenantPathStartingWithAndRequestStatus(String tenantPathPrefix, RequestStatus status);
}
