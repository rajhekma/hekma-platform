-- Flyway Migration V6: Grant the full tenant-owner bundle to every existing SPONSOR/SITE user (decision OD-2),
-- so behaviour is unchanged for users created before per-user authorities existed.

INSERT INTO identity_user_authorities (id, user_id, authority_key)
SELECT gen_random_uuid(), u.id, a.authority_key
FROM identity_users u
CROSS JOIN identity_authorities a
WHERE u.role IN ('SPONSOR', 'SITE')
  AND u.is_deleted = FALSE
ON CONFLICT (user_id, authority_key) DO NOTHING;
