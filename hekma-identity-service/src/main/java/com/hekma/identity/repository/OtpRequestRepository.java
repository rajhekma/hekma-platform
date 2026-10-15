package com.hekma.identity.repository;

import com.hekma.identity.domain.otp.OtpRequestEntity;
import com.hekma.identity.domain.otp.OtpStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface OtpRequestRepository extends JpaRepository<OtpRequestEntity, UUID> {

    Optional<OtpRequestEntity> findByIdAndPhoneNumber(UUID id, String phoneNumber);

    Optional<OtpRequestEntity> findByIdAndEmail(UUID id, String email);

    long countByPhoneNumberAndCreatedAtAfter(String phoneNumber, Instant cutoff);

    long countByEmailAndCreatedAtAfter(String email, Instant cutoff);

    @org.springframework.data.jpa.repository.Query("SELECT COALESCE(SUM(1 + r.resendCount), 0) FROM OtpRequestEntity r WHERE r.phoneNumber = :phoneNumber AND r.createdAt >= :cutoff")
    long countTotalOtpRequestsInWindow(@org.springframework.data.repository.query.Param("phoneNumber") String phoneNumber, @org.springframework.data.repository.query.Param("cutoff") Instant cutoff);

    @org.springframework.data.jpa.repository.Query("SELECT COALESCE(SUM(1 + r.resendCount), 0) FROM OtpRequestEntity r WHERE r.email = :email AND r.createdAt >= :cutoff")
    long countTotalOtpRequestsInWindowByEmail(@org.springframework.data.repository.query.Param("email") String email, @org.springframework.data.repository.query.Param("cutoff") Instant cutoff);

    Optional<OtpRequestEntity> findTopByEmailAndStatusOrderByCreatedAtDesc(String email, OtpStatus status);

    Optional<OtpRequestEntity> findTopByPhoneNumberAndStatusOrderByCreatedAtDesc(String phoneNumber, OtpStatus status);

    Optional<OtpRequestEntity> findTopByEmailOrderByCreatedAtDesc(String email);

    Optional<OtpRequestEntity> findTopByPhoneNumberOrderByCreatedAtDesc(String phoneNumber);

    List<OtpRequestEntity> findByPhoneNumberAndStatusOrderByCreatedAtDesc(String phoneNumber, OtpStatus status);
}
