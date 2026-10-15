package com.hekma.identity.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

/**
 * Append-only record of a privileged action (authority changes, user status changes, tenant lifecycle,
 * invitations). Holds identifiers only, never PHI. Rows are never updated or deleted.
 */
@Entity
@Table(name = "identity_authz_audit_log")
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AuthzAuditLogEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "occurred_at", nullable = false, updatable = false)
    private Instant occurredAt;

    /**
     * Acting user; null for system actions and public self-service flows.
     */
    @Column(name = "actor_id", updatable = false)
    private UUID actorId;

    @Column(name = "action", nullable = false, length = 64, updatable = false)
    private String action;

    @Column(name = "target_type", nullable = false, length = 32, updatable = false)
    private String targetType;

    @Column(name = "target_id", updatable = false)
    private UUID targetId;

    @Column(name = "tenant_id", updatable = false)
    private UUID tenantId;

    @Column(name = "before_value", length = 2048, updatable = false)
    private String beforeValue;

    @Column(name = "after_value", length = 2048, updatable = false)
    private String afterValue;

    @Column(name = "reason", length = 512, updatable = false)
    private String reason;

    @PrePersist
    void onCreate() {
        if (occurredAt == null) {
            occurredAt = Instant.now();
        }
    }
}
