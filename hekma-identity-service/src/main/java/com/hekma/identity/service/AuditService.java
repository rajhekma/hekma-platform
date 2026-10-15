package com.hekma.identity.service;

import com.hekma.identity.domain.AuthzAuditLogEntity;
import com.hekma.identity.repository.AuthzAuditLogRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.UUID;

/**
 * Writes the append-only audit log of privileged actions ({@code identity_authz_audit_log}).
 * Entries carry identifiers and short values only, never PHI. They are written in the caller's transaction,
 * so an action that rolls back leaves no audit entry.
 */
@Service
@Slf4j
public class AuditService {

    public static final String AUTHORITIES_CHANGED = "AUTHORITIES_CHANGED";
    public static final String AUTHORITIES_GRANTED = "AUTHORITIES_GRANTED";
    public static final String USER_STATUS_CHANGED = "USER_STATUS_CHANGED";
    public static final String USER_SOFT_DELETED = "USER_SOFT_DELETED";
    public static final String ADMIN_CREATED = "ADMIN_CREATED";
    public static final String STAFF_INVITED = "STAFF_INVITED";
    public static final String STAFF_INVITATION_ACCEPTED = "STAFF_INVITATION_ACCEPTED";
    public static final String TENANT_REGISTERED = "TENANT_REGISTERED";
    public static final String TENANT_CREATED = "TENANT_CREATED";
    public static final String TENANT_UPDATED = "TENANT_UPDATED";
    public static final String TENANT_STATUS_CHANGED = "TENANT_STATUS_CHANGED";
    public static final String ROLE_AUTHORITIES_CHANGED = "ROLE_AUTHORITIES_CHANGED";
    public static final String PATIENT_INVITED = "PATIENT_INVITED";
    public static final String PATIENT_ASSIGNED = "PATIENT_ASSIGNED";
    public static final String CUSTOM_ROLE_CREATED = "CUSTOM_ROLE_CREATED";
    public static final String CUSTOM_ROLE_UPDATED = "CUSTOM_ROLE_UPDATED";
    public static final String CUSTOM_ROLE_DELETED = "CUSTOM_ROLE_DELETED";
    public static final String CUSTOM_ROLE_ASSIGNED = "CUSTOM_ROLE_ASSIGNED";

    public static final String TARGET_USER = "USER";
    public static final String TARGET_TENANT = "TENANT";
    public static final String TARGET_INVITATION = "INVITATION";
    public static final String TARGET_ROLE = "ROLE";
    public static final String TARGET_CUSTOM_ROLE = "CUSTOM_ROLE";

    private final AuthzAuditLogRepository auditLogRepository;

    public AuditService(AuthzAuditLogRepository auditLogRepository) {
        this.auditLogRepository = auditLogRepository;
    }

    public void record(UUID actorId, String action, String targetType, UUID targetId, UUID tenantId,
                       String before, String after, String reason) {
        auditLogRepository.save(AuthzAuditLogEntity.builder()
                .actorId(actorId)
                .action(action)
                .targetType(targetType)
                .targetId(targetId)
                .tenantId(tenantId)
                .beforeValue(truncate(before, 2048))
                .afterValue(truncate(after, 2048))
                .reason(truncate(reason, 512))
                .build());
        log.info("AUDIT action={} actor={} target={}:{} tenant={}", action, actorId, targetType, targetId, tenantId);
    }

    private static String truncate(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }
}
