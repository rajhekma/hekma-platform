package com.hekma.identity.security;

import java.util.Locale;
import java.util.UUID;

/**
 * Resolves the email used to authenticate an account against Firebase.
 * Firebase can only verify passwords for email/password accounts, so phone-only users
 * receive a synthetic internal login email that is never shown to or used by the user.
 */
public final class AuthEmails {

    public static final String SYNTHETIC_DOMAIN = "phone.hekma.internal";

    private AuthEmails() {
    }

    /**
     * Returns the user's real email when present, otherwise a new synthetic login email.
     */
    public static String resolve(String email) {
        if (email != null && !email.isBlank()) {
            return email.trim().toLowerCase(Locale.ROOT);
        }
        return generateSynthetic();
    }

    public static String generateSynthetic() {
        return "phone-" + UUID.randomUUID() + "@" + SYNTHETIC_DOMAIN;
    }
}
