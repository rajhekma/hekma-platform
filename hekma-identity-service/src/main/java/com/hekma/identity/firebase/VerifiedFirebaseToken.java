package com.hekma.identity.firebase;

/**
 * Result of a successful Firebase ID token verification.
 *
 * @param firebaseUid the Firebase UID the token was issued to
 * @param issuedAt the token issue time (epoch seconds for Firebase tokens; epoch millis for mock tokens)
 */
public record VerifiedFirebaseToken(String firebaseUid, long issuedAt) {
}
