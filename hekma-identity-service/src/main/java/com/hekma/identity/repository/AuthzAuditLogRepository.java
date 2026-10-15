package com.hekma.identity.repository;

import com.hekma.identity.domain.AuthzAuditLogEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

/**
 * Append-only: callers only insert and read.
 */
@Repository
public interface AuthzAuditLogRepository extends JpaRepository<AuthzAuditLogEntity, UUID> {

    List<AuthzAuditLogEntity> findByTargetIdOrderByOccurredAtDesc(UUID targetId);

    List<AuthzAuditLogEntity> findByActionOrderByOccurredAtDesc(String action);
}
