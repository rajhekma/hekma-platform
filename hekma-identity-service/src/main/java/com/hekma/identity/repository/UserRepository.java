package com.hekma.identity.repository;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface UserRepository extends JpaRepository<UserEntity, UUID> {

    Optional<UserEntity> findByEmail(String email);

    Optional<UserEntity> findByFirebaseUid(String firebaseUid);

    @EntityGraph(attributePaths = "tenant")
    @Query("SELECT u FROM UserEntity u WHERE u.firebaseUid = :firebaseUid")
    Optional<UserEntity> findWithTenantByFirebaseUid(@Param("firebaseUid") String firebaseUid);

    Optional<UserEntity> findByAuthEmail(String authEmail);

    Optional<UserEntity> findByPhoneNumber(String phoneNumber);

    boolean existsByEmail(String email);

    boolean existsByPhoneNumber(String phoneNumber);

    boolean existsByRole(Role role);

    List<UserEntity> findAllByOrderByCreatedAtDesc();

    List<UserEntity> findByRoleOrderByCreatedAtDesc(Role role);

    long countByRole(Role role);

    long countByTenant_Id(UUID tenantId);

    org.springframework.data.domain.Page<UserEntity> findByTenant_PathStartingWith(String tenantPathPrefix, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<UserEntity> findByTenant_PathStartingWithAndRole(String tenantPathPrefix, Role role, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<UserEntity> findByRole(Role role, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<UserEntity> findByTenant_Id(UUID tenantId, org.springframework.data.domain.Pageable pageable);

    org.springframework.data.domain.Page<UserEntity> findByTenant_IdAndRole(UUID tenantId, Role role, org.springframework.data.domain.Pageable pageable);
}
