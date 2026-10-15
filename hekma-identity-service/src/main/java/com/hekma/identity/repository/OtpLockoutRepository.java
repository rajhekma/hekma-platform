package com.hekma.identity.repository;

import com.hekma.identity.domain.otp.OtpLockoutEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface OtpLockoutRepository extends JpaRepository<OtpLockoutEntity, UUID> {

    Optional<OtpLockoutEntity> findByPhoneNumber(String phoneNumber);

    Optional<OtpLockoutEntity> findByEmail(String email);

    void deleteByPhoneNumber(String phoneNumber);

    void deleteByEmail(String email);
}
