package com.hekma.identity.repository;

import com.hekma.identity.domain.StaffInvitationEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface StaffInvitationRepository extends JpaRepository<StaffInvitationEntity, UUID> {

    Optional<StaffInvitationEntity> findByTokenHash(String tokenHash);
}
