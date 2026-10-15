-- Flyway Migration V3: Firebase login email for password validation
-- Every account authenticates against Firebase with an email. Users registered with a phone number only
-- receive a synthetic internal login email (e.g. phone-<uuid>@phone.hekma.internal) stored here.
-- Existing phone-only users keep auth_email = NULL until they complete the password reset flow.

ALTER TABLE identity_users ADD COLUMN IF NOT EXISTS auth_email VARCHAR(255);

UPDATE identity_users SET auth_email = email WHERE auth_email IS NULL AND email IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS identity_uq_users_auth_email ON identity_users(auth_email);
