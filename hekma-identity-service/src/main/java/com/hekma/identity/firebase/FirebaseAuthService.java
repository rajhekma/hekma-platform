package com.hekma.identity.firebase;

import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseAuthException;
import com.google.firebase.auth.FirebaseToken;
import com.google.firebase.auth.UserRecord;
import com.hekma.identity.domain.Role;
import com.hekma.identity.exception.FirebaseOperationException;
import com.hekma.identity.exception.InvalidTokenException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

@Slf4j
public class FirebaseAuthService implements FirebaseService {

    private final FirebaseAuth firebaseAuth;
    private final String webApiKey;
    private final RestTemplate restTemplate;

    public FirebaseAuthService(FirebaseAuth firebaseAuth) {
        this(firebaseAuth, null, new RestTemplate());
    }

    public FirebaseAuthService(FirebaseAuth firebaseAuth, String webApiKey) {
        this(firebaseAuth, webApiKey, new RestTemplate());
    }

    public FirebaseAuthService(FirebaseAuth firebaseAuth, String webApiKey, RestTemplate restTemplate) {
        this.firebaseAuth = firebaseAuth;
        this.webApiKey = webApiKey;
        this.restTemplate = restTemplate != null ? restTemplate : new RestTemplate();
    }

    @Override
    public FirebaseUserDto createUser(String email, String password, String displayName, Role role) {
        log.info("Creating user in Firebase Auth with email: {} and role: {}", email, role);
        try {
            UserRecord.CreateRequest request = new UserRecord.CreateRequest()
                    .setPassword(password)
                    .setEmailVerified(false);

            if (email != null && !email.isBlank()) {
                request.setEmail(email.trim());
            }

            if (displayName != null && !displayName.trim().isEmpty()) {
                request.setDisplayName(displayName.trim());
            }

            UserRecord userRecord = firebaseAuth.createUser(request);
            assignRoleClaim(userRecord.getUid(), role);

            return FirebaseUserDto.builder()
                    .uid(userRecord.getUid())
                    .email(userRecord.getEmail())
                    .displayName(userRecord.getDisplayName())
                    .role(role)
                    .build();
        } catch (FirebaseAuthException e) {
            log.error("Firebase error while creating user {}: code={}, message={}", email, e.getAuthErrorCode(), e.getMessage());
            if ("EMAIL_ALREADY_EXISTS".equalsIgnoreCase(String.valueOf(e.getAuthErrorCode())) ||
                    e.getMessage().toLowerCase().contains("already in use") ||
                    e.getMessage().toLowerCase().contains("already exists")) {
                throw new UserAlreadyExistsException("A user with email '" + email + "' already exists in Firebase.");
            }
            throw new FirebaseOperationException("Failed to create user in Firebase: " + e.getMessage(), e);
        }
    }

    @Override
    public void assignRoleClaim(String firebaseUid, Role role) {
        assignClaims(firebaseUid, role, null);
    }

    @Override
    public void assignClaims(String firebaseUid, Role role, java.util.UUID tenantId) {
        log.info("Assigning custom claim role: {}, tenantId: {} for Firebase UID: {}", role, tenantId, firebaseUid);
        try {
            Map<String, Object> claims = new HashMap<>();
            claims.put("role", role.name());
            if (tenantId != null) {
                claims.put("tenantId", tenantId.toString());
            }
            firebaseAuth.setCustomUserClaims(firebaseUid, claims);
        } catch (FirebaseAuthException e) {
            log.error("Failed to assign claims to Firebase user {}: {}", firebaseUid, e.getMessage());
            throw new FirebaseOperationException("Failed to set custom claims in Firebase: " + e.getMessage(), e);
        }
    }


    @Override
    public void deleteUser(String firebaseUid) {
        log.info("Deleting user from Firebase Auth: {}", firebaseUid);
        try {
            firebaseAuth.deleteUser(firebaseUid);
        } catch (FirebaseAuthException e) {
            log.warn("Failed to delete user {} from Firebase during compensating rollback: {}", firebaseUid, e.getMessage());
        }
    }

    @Override
    public Optional<FirebaseUserDto> getUserByEmail(String email) {
        if (email == null || email.isBlank()) {
            return Optional.empty();
        }
        try {
            UserRecord record = firebaseAuth.getUserByEmail(email);
            Role role = null;
            Object roleClaim = record.getCustomClaims().get("role");
            if (roleClaim != null) {
                try {
                    role = Role.valueOf(roleClaim.toString());
                } catch (IllegalArgumentException ignored) {
                }
            }
            return Optional.of(FirebaseUserDto.builder()
                    .uid(record.getUid())
                    .email(record.getEmail())
                    .displayName(record.getDisplayName())
                    .role(role)
                    .build());
        } catch (FirebaseAuthException e) {
            return Optional.empty();
        }
    }

    @Override
    public FirebaseTokenRefreshResponse refreshToken(String refreshToken) {
        if (webApiKey == null || webApiKey.trim().isEmpty()) {
            log.error("Firebase Web API Key is not configured for token refresh.");
            throw new FirebaseOperationException("Firebase Web API Key is not configured. Please set 'firebase.web-api-key' or environment variable 'FIREBASE_WEB_API_KEY'.");
        }

        String url = "https://securetoken.googleapis.com/v1/token?key=" + webApiKey.trim();

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);

            MultiValueMap<String, String> body = new LinkedMultiValueMap<>();
            body.add("grant_type", "refresh_token");
            body.add("refresh_token", refreshToken);

            HttpEntity<MultiValueMap<String, String>> entity = new HttpEntity<>(body, headers);

            ResponseEntity<GoogleTokenResponse> response = restTemplate.postForEntity(url, entity, GoogleTokenResponse.class);

            GoogleTokenResponse tokenBody = response.getBody();
            if (tokenBody == null || tokenBody.getIdToken() == null) {
                throw new InvalidTokenException("Failed to obtain refreshed ID token from Firebase STS.");
            }

            return FirebaseTokenRefreshResponse.builder()
                    .idToken(tokenBody.getIdToken())
                    .refreshToken(tokenBody.getRefreshToken())
                    .tokenType(tokenBody.getTokenType() != null ? tokenBody.getTokenType() : "Bearer")
                    .expiresIn(tokenBody.getExpiresIn() != null ? tokenBody.getExpiresIn() : 3600L)
                    .firebaseUid(tokenBody.getUserId())
                    .projectId(tokenBody.getProjectId())
                    .build();

        } catch (HttpClientErrorException e) {
            String responseBody = e.getResponseBodyAsString();
            log.warn("Firebase STS error during token refresh: status={}, body={}", e.getStatusCode(), responseBody);
            if (responseBody.contains("TOKEN_EXPIRED") || responseBody.contains("INVALID_REFRESH_TOKEN")) {
                throw new InvalidTokenException("The refresh token is invalid or expired. Please sign in again.");
            }
            if (responseBody.contains("USER_DISABLED") || responseBody.contains("USER_NOT_FOUND")) {
                throw new InvalidTokenException("The user associated with this token has been disabled or deleted.");
            }
            throw new InvalidTokenException("Token refresh rejected by authentication provider: " + e.getStatusText());
        } catch (InvalidTokenException e) {
            throw e;
        } catch (Exception e) {
            log.error("Unexpected error during Firebase token refresh: {}", e.getMessage(), e);
            throw new FirebaseOperationException("Failed to refresh token with Firebase: " + e.getMessage(), e);
        }
    }

    @Override
    public String createCustomToken(String firebaseUid, Map<String, Object> claims) {
        log.info("Creating custom token for Firebase UID: {}", firebaseUid);
        try {
            if (claims != null && !claims.isEmpty()) {
                return firebaseAuth.createCustomToken(firebaseUid, claims);
            } else {
                return firebaseAuth.createCustomToken(firebaseUid);
            }
        } catch (FirebaseAuthException e) {
            log.error("Failed to create custom token for Firebase UID {}: {}", firebaseUid, e.getMessage());
            throw new FirebaseOperationException("Failed to generate custom token: " + e.getMessage(), e);
        }
    }

    @Override
    public String createCustomToken(String firebaseUid) {
        return createCustomToken(firebaseUid, null);
    }

    @Override
    public FirebaseSignInResponse signInWithPassword(String email, String password) {
        if (email == null || email.isBlank() || password == null || password.isBlank()) {
            throw new InvalidTokenException("Email and password must not be blank.");
        }

        if (webApiKey == null || webApiKey.trim().isEmpty()) {
            // Fail closed: without the Web API key the password cannot be verified.
            log.error("Firebase Web API Key is not configured. Password sign-in is unavailable.");
            throw new FirebaseOperationException("Firebase Web API Key is not configured. Please set 'firebase.web-api-key' or environment variable 'FIREBASE_WEB_API_KEY'.");
        }

        String url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + webApiKey.trim();
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            Map<String, Object> body = Map.of(
                    "email", email.trim(),
                    "password", password,
                    "returnSecureToken", true
            );

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(body, headers);
            ResponseEntity<GoogleSignInResponse> response = restTemplate.postForEntity(url, entity, GoogleSignInResponse.class);

            GoogleSignInResponse respBody = response.getBody();
            if (respBody == null || respBody.getIdToken() == null) {
                throw new InvalidTokenException("Invalid email or password.");
            }

            return FirebaseSignInResponse.builder()
                    .idToken(respBody.getIdToken())
                    .refreshToken(respBody.getRefreshToken())
                    .expiresIn(respBody.getExpiresIn() != null ? Long.parseLong(respBody.getExpiresIn()) : 3600L)
                    .firebaseUid(respBody.getLocalId())
                    .email(respBody.getEmail())
                    .build();

        } catch (HttpClientErrorException e) {
            String responseBody = e.getResponseBodyAsString();
            log.warn("Firebase sign in failure: status={}, body={}", e.getStatusCode(), responseBody);
            if (responseBody.contains("EMAIL_NOT_FOUND") || responseBody.contains("INVALID_PASSWORD") ||
                    responseBody.contains("INVALID_LOGIN_CREDENTIALS")) {
                throw new InvalidTokenException("Invalid email or password.");
            }
            if (responseBody.contains("USER_DISABLED")) {
                throw new InvalidTokenException("User account has been disabled in Firebase.");
            }
            throw new InvalidTokenException("Authentication failed: " + e.getStatusText());
        } catch (InvalidTokenException e) {
            throw e;
        } catch (Exception e) {
            log.error("Unexpected error during Firebase password sign in: {}", e.getMessage(), e);
            throw new FirebaseOperationException("Failed to authenticate with Firebase: " + e.getMessage(), e);
        }
    }

    @Override
    public void updatePassword(String firebaseUid, String password) {
        log.info("Updating password in Firebase Auth for UID: {}", firebaseUid);
        try {
            UserRecord.UpdateRequest request = new UserRecord.UpdateRequest(firebaseUid)
                    .setPassword(password);
            firebaseAuth.updateUser(request);
        } catch (FirebaseAuthException e) {
            log.error("Failed to update password for Firebase UID: {}", firebaseUid, e);
            throw new FirebaseOperationException("Failed to update password in Firebase Auth: " + e.getMessage(), e);
        }
    }

    @Override
    public void updateAuthEmail(String firebaseUid, String authEmail) {
        log.info("Updating login email in Firebase Auth for UID: {}", firebaseUid);
        try {
            firebaseAuth.updateUser(new UserRecord.UpdateRequest(firebaseUid).setEmail(authEmail));
        } catch (FirebaseAuthException e) {
            log.error("Failed to update login email for Firebase UID {}: {}", firebaseUid, e.getMessage());
            throw new FirebaseOperationException("Failed to update login email in Firebase Auth: " + e.getMessage(), e);
        }
    }

    @Override
    public VerifiedFirebaseToken verifyIdToken(String idToken) {
        try {
            FirebaseToken token = firebaseAuth.verifyIdToken(idToken, true);
            Object iat = token.getClaims().get("iat");
            long issuedAt = iat instanceof Number n ? n.longValue() : 0L;
            return new VerifiedFirebaseToken(token.getUid(), issuedAt);
        } catch (FirebaseAuthException e) {
            log.debug("Firebase ID token rejected: code={}, message={}", e.getAuthErrorCode(), e.getMessage());
            throw new InvalidTokenException("The access token is invalid, expired or revoked.");
        } catch (IllegalArgumentException e) {
            throw new InvalidTokenException("The access token is malformed.");
        }
    }

    @Override
    public FirebaseSignInResponse signInWithCustomToken(String customToken) {
        if (webApiKey == null || webApiKey.trim().isEmpty()) {
            log.error("Firebase Web API Key is not configured. Custom token exchange is unavailable.");
            throw new FirebaseOperationException("Firebase Web API Key is not configured. Please set 'firebase.web-api-key' or environment variable 'FIREBASE_WEB_API_KEY'.");
        }

        String url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=" + webApiKey.trim();
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            Map<String, Object> body = Map.of(
                    "token", customToken,
                    "returnSecureToken", true
            );

            ResponseEntity<GoogleSignInResponse> response = restTemplate.postForEntity(url, new HttpEntity<>(body, headers), GoogleSignInResponse.class);
            GoogleSignInResponse respBody = response.getBody();
            if (respBody == null || respBody.getIdToken() == null) {
                throw new InvalidTokenException("Failed to obtain an ID token from Firebase.");
            }

            return FirebaseSignInResponse.builder()
                    .idToken(respBody.getIdToken())
                    .refreshToken(respBody.getRefreshToken())
                    .expiresIn(respBody.getExpiresIn() != null ? Long.parseLong(respBody.getExpiresIn()) : 3600L)
                    .firebaseUid(respBody.getLocalId())
                    .email(respBody.getEmail())
                    .build();
        } catch (HttpClientErrorException e) {
            log.warn("Firebase custom token exchange failure: status={}, body={}", e.getStatusCode(), e.getResponseBodyAsString());
            throw new InvalidTokenException("Token issuance rejected by authentication provider: " + e.getStatusText());
        } catch (InvalidTokenException e) {
            throw e;
        } catch (Exception e) {
            log.error("Unexpected error during Firebase custom token exchange: {}", e.getMessage(), e);
            throw new FirebaseOperationException("Failed to exchange custom token with Firebase: " + e.getMessage(), e);
        }
    }

    @Override
    public void revokeRefreshTokens(String firebaseUid) {
        log.info("Revoking all refresh tokens for Firebase UID: {}", firebaseUid);
        try {
            firebaseAuth.revokeRefreshTokens(firebaseUid);
        } catch (FirebaseAuthException e) {
            log.error("Failed to revoke refresh tokens for Firebase UID {}: {}", firebaseUid, e.getMessage());
            throw new FirebaseOperationException("Failed to revoke sessions in Firebase Auth: " + e.getMessage(), e);
        }
    }
}
