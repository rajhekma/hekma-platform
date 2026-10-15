package com.hekma.identity.domain;

import java.util.Arrays;
import java.util.EnumSet;
import java.util.Optional;
import java.util.Set;

/**
 * Fine-grained tenant authorities (RBAC Phase 3). Granted per SPONSOR/SITE user and always evaluated within the
 * user's tenant subtree. Platform administrators hold every authority implicitly; patients hold none.
 * <p>
 * The catalogue is mirrored in {@code identity_authorities} (seeded by Flyway); adding an authority is a migration
 * plus a new constant here.
 */
public enum Authority {

    TENANT_READ("tenant:read", "View Tenant Hierarchy", "Tenant Governance", "View own tenant and descendant tenants"),
    TENANT_UPDATE("tenant:update", "Update Tenant Settings", "Tenant Governance", "Edit profile and settings of own or descendant tenants"),
    SUBTENANT_CREATE("subtenant:create", "Create Sub-Tenants", "Tenant Governance", "Create sub-tenants under own or descendant tenants"),
    SUBTENANT_MANAGE("subtenant:manage", "Manage Sub-Tenants", "Tenant Governance", "Suspend or activate descendant tenants"),
    USER_READ("user:read", "View User Roster", "User Management", "View users in own and descendant tenants"),
    USER_INVITE("user:invite", "Invite Staff Members", "User Management", "Invite SPONSOR/SITE users into own and descendant tenants"),
    USER_MANAGE("user:manage", "Manage User Accounts", "User Management", "Activate, deactivate or soft-delete users in own and descendant tenants"),
    AUTHORITY_ASSIGN("authority:assign", "Assign User Permissions", "User Management", "Grant or revoke authorities (never beyond one's own)"),
    PATIENT_CREATE("patient:create", "Enroll & Invite Patients", "Clinical & Patients", "Create and invite patient profiles"),
    PATIENT_READ("patient:read", "View Patient Records", "Clinical & Patients", "View patients in own and descendant tenants"),
    PATIENT_UPDATE("patient:update", "Update Patient Details", "Clinical & Patients", "Update patient profile data"),
    PATIENT_ASSIGN("patient:assign", "Reassign Patients", "Clinical & Patients", "Reassign patients within own subtree"),
    ROLE_READ("role:read", "View Custom Roles", "Role Governance", "View custom roles in own or ancestor tenants"),
    ROLE_CREATE("role:create", "Create Custom Roles", "Role Governance", "Create custom roles within own tenant subtree"),
    ROLE_UPDATE("role:update", "Update Custom Roles", "Role Governance", "Modify custom role details and authority bundles"),
    ROLE_DELETE("role:delete", "Delete Custom Roles", "Role Governance", "Delete custom roles in own tenant"),
    ROLE_ASSIGN("role:assign", "Assign Custom Roles", "Role Governance", "Assign custom roles to users in own or descendant tenants");

    /**
     * Authorities granted to a tenant's first user (registration owner, sub-tenant owner) and backfilled to
     * pre-existing SPONSOR/SITE users (OD-2).
     */
    public static final Set<Authority> OWNER_BUNDLE = EnumSet.allOf(Authority.class);

    /**
     * Authorities given to an invited user when the inviter does not specify any (always capped by the inviter's own).
     */
    public static final Set<Authority> DEFAULT_INVITE_BUNDLE = EnumSet.of(TENANT_READ, PATIENT_READ, PATIENT_CREATE);

    private final String key;
    private final String displayName;
    private final String category;
    private final String description;

    Authority(String key, String displayName, String category, String description) {
        this.key = key;
        this.displayName = displayName;
        this.category = category;
        this.description = description;
    }

    /**
     * Stable key, e.g. {@code patient:read}; used in the database, the API and {@code hasAuthority('…')} rules.
     */
    public String key() {
        return key;
    }

    public String displayName() {
        return displayName;
    }

    public String category() {
        return category;
    }

    public String description() {
        return description;
    }

    public static Optional<Authority> fromKey(String key) {
        return Arrays.stream(values()).filter(a -> a.key.equals(key)).findFirst();
    }
}
