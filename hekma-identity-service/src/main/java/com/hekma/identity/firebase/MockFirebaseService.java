package com.hekma.identity.firebase;

import com.hekma.identity.domain.Role;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import lombok.extern.slf4j.Slf4j;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory stand-in for Firebase Auth, used only when {@code firebase.mock-mode=true}.
 * <p>
 * ID tokens have the deterministic form {@code mock-id-token:<firebaseUid>:<issuedAtEpochMillis>}
 * (see {@link #idTokenFor(String)}). Passwords are verified for users created through this mock.
 */
@Slf4j
public class MockFirebaseService implements FirebaseService {

    public static final String ID_TOKEN_PREFIX = "mock-id-token:";
    private static final String REFRESH_TOKEN_PREFIX = "mock-refresh-token-";

    private final Map<String, FirebaseUserDto> usersByEmail = new ConcurrentHashMap<>();
    private final Map<String, FirebaseUserDto> usersByUid = new ConcurrentHashMap<>();
    private final Map<String, String> passwordsByUid = new ConcurrentHashMap<>();
    private final Map<String, Long> revokedAtByUid = new ConcurrentHashMap<>();

    public MockFirebaseService() {
        log.warn(">>> Using MOCK FirebaseService: Users will be registered in-memory instead of live Firebase. <<<");
    }

    /**
     * Builds a mock ID token for the given Firebase UID, issued now.
     */
    public static String idTokenFor(String firebaseUid) {
        return ID_TOKEN_PREFIX + firebaseUid + ":" + System.currentTimeMillis();
    }

    private static String refreshTokenFor(String firebaseUid) {
        return REFRESH_TOKEN_PREFIX + firebaseUid + ":" + System.currentTimeMillis();
    }

    @Override
    public FirebaseUserDto createUser(String email, String password, String displayName, Role role) {
        log.info("[MOCK] Creating user in mock Firebase: email={}, role={}", email, role);
        if (email != null && usersByEmail.containsKey(email.toLowerCase())) {
            throw new UserAlreadyExistsException("A user with email '" + email + "' already exists in Firebase (Mock).");
        }

        String uid = "mock-fb-" + UUID.randomUUID();
        String safeEmail = (email != null) ? email.toLowerCase() : null;
        FirebaseUserDto userDto = FirebaseUserDto.builder()
                .uid(uid)
                .email(safeEmail)
                .displayName(displayName)
                .role(role)
                .build();

        if (safeEmail != null) {
            usersByEmail.put(safeEmail, userDto);
        }
        usersByUid.put(uid, userDto);
        if (password != null) {
            passwordsByUid.put(uid, password);
        }
        return userDto;
    }

    @Override
    public void assignRoleClaim(String firebaseUid, Role role) {
        assignClaims(firebaseUid, role, null);
    }

    @Override
    public void assignClaims(String firebaseUid, Role role, UUID tenantId) {
        log.info("[MOCK] Assigning role claim {} and tenantId {} to UID {}", role, tenantId, firebaseUid);
        FirebaseUserDto user = usersByUid.get(firebaseUid);
        if (user != null) {
            user.setRole(role);
        }
    }

    @Override
    public void deleteUser(String firebaseUid) {
        log.info("[MOCK] Deleting user with UID {}", firebaseUid);
        FirebaseUserDto user = usersByUid.remove(firebaseUid);
        passwordsByUid.remove(firebaseUid);
        if (user != null && user.getEmail() != null) {
            usersByEmail.remove(user.getEmail());
        }
    }

    @Override
    public Optional<FirebaseUserDto> getUserByEmail(String email) {
        return Optional.ofNullable(usersByEmail.get(email.toLowerCase()));
    }

    @Override
    public FirebaseTokenRefreshResponse refreshToken(String refreshToken) {
        log.info("[MOCK] Refreshing token");
        if (refreshToken == null || refreshToken.trim().isEmpty()) {
            throw new InvalidTokenException("Refresh token must not be blank.");
        }

        String token = refreshToken.trim();
        int separator = token.lastIndexOf(':');
        if (!token.startsWith(REFRESH_TOKEN_PREFIX) || separator < REFRESH_TOKEN_PREFIX.length()) {
            throw new InvalidTokenException("The refresh token is invalid or expired. Please sign in again.");
        }

        String uid = token.substring(REFRESH_TOKEN_PREFIX.length(), separator);
        long issuedAt;
        try {
            issuedAt = Long.parseLong(token.substring(separator + 1));
        } catch (NumberFormatException e) {
            throw new InvalidTokenException("The refresh token is invalid or expired. Please sign in again.");
        }
        Long revokedAt = revokedAtByUid.get(uid);
        if (revokedAt != null && issuedAt < revokedAt) {
            throw new InvalidTokenException("The refresh token is invalid or expired. Please sign in again.");
        }

        return FirebaseTokenRefreshResponse.builder()
                .idToken(idTokenFor(uid))
                .refreshToken(refreshTokenFor(uid))
                .tokenType("Bearer")
                .expiresIn(3600L)
                .firebaseUid(uid)
                .projectId("mock-firebase-project")
                .build();
    }

    @Override
    public String createCustomToken(String firebaseUid, Map<String, Object> claims) {
        log.info("[MOCK] Creating custom token for Firebase UID: {}", firebaseUid);
        if (claims != null && claims.containsKey("tenant_id")) {
            throw new IllegalArgumentException("developerClaims must not contain a reserved key: tenant_id");
        }
        return "mock-custom-token-" + firebaseUid;
    }

    @Override
    public String createCustomToken(String firebaseUid) {
        return createCustomToken(firebaseUid, null);
    }

    @Override
    public FirebaseSignInResponse signInWithPassword(String email, String password) {
        log.info("[MOCK] Signing in with password for email: {}", email);
        if (email == null || email.trim().isEmpty() || password == null || password.trim().isEmpty()) {
            throw new InvalidTokenException("Email and password must not be blank.");
        }

        String safeEmail = email.toLowerCase().trim();
        FirebaseUserDto user = usersByEmail.get(safeEmail);
        if (user == null || !password.equals(passwordsByUid.get(user.getUid()))) {
            throw new InvalidTokenException("Invalid email or password.");
        }

        return FirebaseSignInResponse.builder()
                .idToken(idTokenFor(user.getUid()))
                .refreshToken(refreshTokenFor(user.getUid()))
                .firebaseUid(user.getUid())
                .email(safeEmail)
                .expiresIn(3600L)
                .build();
    }

    @Override
    public void updatePassword(String firebaseUid, String password) {
        log.info("[MOCK] Password updated in mock Firebase for UID: {}", firebaseUid);
        passwordsByUid.put(firebaseUid, password);
    }

    @Override
    public void updateAuthEmail(String firebaseUid, String authEmail) {
        log.info("[MOCK] Login email updated in mock Firebase for UID: {}", firebaseUid);
        FirebaseUserDto user = usersByUid.get(firebaseUid);
        if (user == null) {
            user = FirebaseUserDto.builder().uid(firebaseUid).build();
            usersByUid.put(firebaseUid, user);
        }
        if (user.getEmail() != null) {
            usersByEmail.remove(user.getEmail());
        }
        String safeEmail = authEmail.toLowerCase();
        user.setEmail(safeEmail);
        usersByEmail.put(safeEmail, user);
    }

    @Override
    public VerifiedFirebaseToken verifyIdToken(String idToken) {
        if (idToken == null || !idToken.startsWith(ID_TOKEN_PREFIX)) {
            throw new InvalidTokenException("The access token is invalid, expired or revoked.");
        }

        String[] parts = idToken.substring(ID_TOKEN_PREFIX.length()).split(":");
        if (parts.length != 2 || parts[0].isBlank()) {
            throw new InvalidTokenException("The access token is malformed.");
        }

        long issuedAt;
        try {
            issuedAt = Long.parseLong(parts[1]);
        } catch (NumberFormatException e) {
            throw new InvalidTokenException("The access token is malformed.");
        }

        Long revokedAt = revokedAtByUid.get(parts[0]);
        if (revokedAt != null && issuedAt < revokedAt) {
            throw new InvalidTokenException("The access token is invalid, expired or revoked.");
        }
        return new VerifiedFirebaseToken(parts[0], issuedAt);
    }

    @Override
    public FirebaseSignInResponse signInWithCustomToken(String customToken) {
        String prefix = "mock-custom-token-";
        if (customToken == null || !customToken.startsWith(prefix)) {
            throw new InvalidTokenException("Invalid custom token.");
        }
        String uid = customToken.substring(prefix.length());
        FirebaseUserDto user = usersByUid.get(uid);
        return FirebaseSignInResponse.builder()
                .idToken(idTokenFor(uid))
                .refreshToken(refreshTokenFor(uid))
                .firebaseUid(uid)
                .email(user != null ? user.getEmail() : null)
                .expiresIn(3600L)
                .build();
    }

    @Override
    public void revokeRefreshTokens(String firebaseUid) {
        log.info("[MOCK] Revoking sessions for UID {}", firebaseUid);
        revokedAtByUid.put(firebaseUid, System.currentTimeMillis());
    }
}
