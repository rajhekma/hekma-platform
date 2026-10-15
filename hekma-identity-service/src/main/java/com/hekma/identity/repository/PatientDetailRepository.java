package com.hekma.identity.repository;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.UserEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface PatientDetailRepository extends JpaRepository<PatientDetailEntity, UUID> {

    Optional<PatientDetailEntity> findByUserId(UUID userId);

    Optional<PatientDetailEntity> findByInvitationCode(String invitationCode);

    List<PatientDetailEntity> findByInvitationCodeIgnoreCase(String invitationCode);

    List<PatientDetailEntity> findByUserIn(List<UserEntity> users);

    Optional<PatientDetailEntity> findByUser(UserEntity user);

    Optional<PatientDetailEntity> findByPhoneNumber(String phoneNumber);

    boolean existsByPhoneNumber(String phoneNumber);

    org.springframework.data.domain.Page<PatientDetailEntity> findByUser_Tenant_Id(UUID tenantId, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<PatientDetailEntity> findByUser_Tenant_IdAndAssignedUserId(UUID tenantId, UUID assignedUserId, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<PatientDetailEntity> findByUser_Tenant_PathStartingWith(String tenantPathPrefix, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<PatientDetailEntity> findByUser_Tenant_PathStartingWithAndAssignedUserId(String tenantPathPrefix, UUID assignedUserId, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<PatientDetailEntity> findByAssignedUserId(UUID assignedUserId, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<PatientDetailEntity> findByUser_Tenant_IdAndAssignedUserIsNull(UUID tenantId, org.springframework.data.domain.Pageable pageable);
}
