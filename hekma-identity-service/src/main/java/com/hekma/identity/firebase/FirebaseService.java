package com.hekma.identity.firebase;

import com.hekma.identity.domain.Role;

import java.util.Map;
import java.util.Optional;

public interface FirebaseService {

    /**
     * Creates a user in Firebase Auth and assigns the specified role as a custom claim.
     *
     * @param email user's email address
     * @param password user's plaintext password
     * @param displayName user's full name or display name (optional)
     * @param role user's assigned role
     * @return FirebaseUserDto containing the newly created Firebase UID and details
     */
    FirebaseUserDto createUser(String email, String password, String displayName, Role role);

    /**
     * Updates or assigns the role custom claim in Firebase for an existing user.
     *
     * @param firebaseUid the Firebase UID
     * @param role the role to assign
     */
    void assignRoleClaim(String firebaseUid, Role role);

    /**
     * Updates or assigns role and tenant_id custom claims in Firebase for an existing user.
     *
     * @param firebaseUid the Firebase UID
     * @param role the role to assign
     * @param tenantId the tenant ID to assign (or null if platform-global)
     */
    void assignClaims(String firebaseUid, Role role, java.util.UUID tenantId);


    /**
     * Deletes a user from Firebase Auth.
     * Used for compensating transactions if local database persistence fails.
     *
     * @param firebaseUid the Firebase UID
     */
    void deleteUser(String firebaseUid);

    /**
     * Retrieves an existing Firebase user by email, if present.
     *
     * @param email the email address
     * @return optional FirebaseUserDto
     */
    Optional<FirebaseUserDto> getUserByEmail(String email);

    /**
     * Refreshes an expired Firebase ID token using a valid OAuth2 refresh token.
     *
     * @param refreshToken the OAuth2 refresh token
     * @return FirebaseTokenRefreshResponse containing the new ID token, refresh token, and user details
     */
    FirebaseTokenRefreshResponse refreshToken(String refreshToken);

    /**
     * Creates a Firebase custom token for a given Firebase UID and custom claims.
     *
     * @param firebaseUid the Firebase UID
     * @param claims custom claims map
     * @return Firebase custom token string
     */
    String createCustomToken(String firebaseUid, Map<String, Object> claims);

    /**
     * Creates a Firebase custom token for a given Firebase UID.
     *
     * @param firebaseUid the Firebase UID
     * @return Firebase custom token string
     */
    String createCustomToken(String firebaseUid);

    /**
     * Authenticates a user with email and password via Firebase Auth.
     *
     * @param email user's email address
     * @param password user's password
     * @return FirebaseSignInResponse containing ID token, refresh token, and Firebase UID
     */
    FirebaseSignInResponse signInWithPassword(String email, String password);

    /**
     * Updates a user's password in Firebase Auth.
     *
     * @param firebaseUid the Firebase UID
     * @param password the new password
     */
    void updatePassword(String firebaseUid, String password);

    /**
     * Updates the login email of a Firebase user (used to assign a synthetic auth email
     * to phone-only accounts so their password can be validated by Firebase).
     *
     * @param firebaseUid the Firebase UID
     * @param authEmail the new login email
     */
    void updateAuthEmail(String firebaseUid, String authEmail);

    /**
     * Verifies a Firebase ID token (signature, issuer, audience, expiry and revocation status).
     *
     * @param idToken the Firebase ID token presented as a Bearer token
     * @return the verified token details
     * @throws com.hekma.identity.exception.InvalidTokenException if the token is invalid, expired or revoked
     */
    VerifiedFirebaseToken verifyIdToken(String idToken);

    /**
     * Exchanges a Firebase custom token for an ID token and refresh token.
     *
     * @param customToken the Firebase custom token minted by this service
     * @return FirebaseSignInResponse containing ID token, refresh token, and Firebase UID
     */
    FirebaseSignInResponse signInWithCustomToken(String customToken);

    /**
     * Revokes all refresh tokens of a user. Combined with revocation-checked ID token
     * verification, this terminates every existing session of the user.
     *
     * @param firebaseUid the Firebase UID
     */
    void revokeRefreshTokens(String firebaseUid);
}
