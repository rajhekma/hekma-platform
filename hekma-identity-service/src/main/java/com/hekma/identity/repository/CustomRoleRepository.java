package com.hekma.identity.repository;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.CustomRoleEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

@Repository
public interface CustomRoleRepository extends JpaRepository<CustomRoleEntity, UUID> {

    Optional<CustomRoleEntity> findByIdAndIsDeletedFalse(UUID id);

    boolean existsByTenant_IdAndCodeIgnoreCaseAndIsDeletedFalse(UUID tenantId, String code);

    boolean existsByTenantIsNullAndCodeIgnoreCaseAndIsDeletedFalse(String code);

    Optional<CustomRoleEntity> findByTenant_IdAndCodeIgnoreCaseAndIsDeletedFalse(UUID tenantId, String code);

    Optional<CustomRoleEntity> findByTenantIsNullAndCodeIgnoreCaseAndIsDeletedFalse(String code);

    List<CustomRoleEntity> findByTenant_IdAndIsDeletedFalse(UUID tenantId);

    @Query("SELECT r FROM CustomRoleEntity r WHERE r.isDeleted = false AND r.tenant IS NULL ORDER BY r.name ASC")
    List<CustomRoleEntity> findGlobalRoles();

    @Query("SELECT r FROM CustomRoleEntity r WHERE r.isDeleted = false AND " +
           "(r.tenant IS NULL OR r.tenantPath LIKE CONCAT(:tenantPathPrefix, '%') OR :callerTenantPath LIKE CONCAT(r.tenantPath, '%')) " +
           "ORDER BY r.name ASC")
    List<CustomRoleEntity> findVisibleRoles(@Param("tenantPathPrefix") String tenantPathPrefix,
                                            @Param("callerTenantPath") String callerTenantPath);

    @Query("SELECT r FROM CustomRoleEntity r WHERE r.isDeleted = false ORDER BY r.name ASC")
    List<CustomRoleEntity> findAllActiveRoles();

    @Query("SELECT cra.authority FROM UserCustomRoleEntity ucr " +
           "JOIN ucr.customRole cr " +
           "JOIN cr.roleAuthorities cra " +
           "WHERE ucr.user.id = :userId AND cr.isActive = true AND cr.isDeleted = false")
    Set<Authority> findAuthoritiesByUserId(@Param("userId") UUID userId);

    @Query("SELECT cr.code FROM UserCustomRoleEntity ucr " +
           "JOIN ucr.customRole cr " +
           "WHERE ucr.user.id = :userId AND cr.isActive = true AND cr.isDeleted = false")
    Set<String> findRoleCodesByUserId(@Param("userId") UUID userId);
}
