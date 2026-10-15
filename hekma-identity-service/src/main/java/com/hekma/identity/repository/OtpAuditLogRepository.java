package com.hekma.identity.repository;

import com.hekma.identity.domain.otp.OtpAuditLogEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface OtpAuditLogRepository extends JpaRepository<OtpAuditLogEntity, UUID> {

    List<OtpAuditLogEntity> findByPhoneNumberOrderByCreatedAtDesc(String phoneNumber);

    List<OtpAuditLogEntity> findByAttemptIdOrderByCreatedAtAsc(UUID attemptId);
}
