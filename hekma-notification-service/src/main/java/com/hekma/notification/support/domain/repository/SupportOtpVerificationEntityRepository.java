package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportOtpVerificationEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface SupportOtpVerificationEntityRepository extends JpaRepository<SupportOtpVerificationEntity, Long> {

    Optional<SupportOtpVerificationEntity> findByChallengeId(String challengeId);

    Optional<SupportOtpVerificationEntity> findBySessionToken(String sessionToken);

    Optional<SupportOtpVerificationEntity> findTopByEmailOrderByCreatedTsDesc(String email);
}
