-- Flyway Migration V11: Cleanup obsolete prototype 'role:manage' authority key

DELETE FROM identity_user_authorities WHERE authority_key = 'role:manage';
DELETE FROM identity_role_authorities WHERE authority_key = 'role:manage';
DELETE FROM identity_custom_role_authorities WHERE authority_key = 'role:manage';
DELETE FROM identity_authorities WHERE authority_key = 'role:manage';
