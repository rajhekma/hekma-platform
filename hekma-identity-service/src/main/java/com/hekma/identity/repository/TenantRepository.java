package com.hekma.identity.repository;

import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface TenantRepository extends JpaRepository<TenantEntity, UUID>, JpaSpecificationExecutor<TenantEntity> {

    Optional<TenantEntity> findBySlug(String slug);

    Optional<TenantEntity> findByDefaultTenantTrue();

    boolean existsBySlug(String slug);

    boolean existsByDefaultTenantTrue();

    Page<TenantEntity> findByTenantType(TenantType tenantType, Pageable pageable);

    Page<TenantEntity> findByStatus(TenantStatus status, Pageable pageable);

    Page<TenantEntity> findByTenantTypeAndStatus(TenantType tenantType, TenantStatus status, Pageable pageable);

    List<TenantEntity> findByParent_IdOrderByNameAsc(UUID parentId);

    /**
     * True when any of the given tenants is not in the given status (used to check a tenant's ancestor chain).
     */
    boolean existsByIdInAndStatusNot(Collection<UUID> ids, TenantStatus status);
}
