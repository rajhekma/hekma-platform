package com.hekma.identity.firebase;

import com.google.auth.oauth2.GoogleCredentials;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.auth.FirebaseAuth;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

import java.io.InputStream;

@Configuration
@Slf4j
public class FirebaseConfig {

    private final FirebaseProperties properties;
    private final ResourceLoader resourceLoader;

    public FirebaseConfig(FirebaseProperties properties, ResourceLoader resourceLoader) {
        this.properties = properties;
        this.resourceLoader = resourceLoader;
    }

    @Bean
    public FirebaseService firebaseService() {
        if (properties.isMockMode()) {
            log.info("Firebase mock mode is enabled via configuration.");
            return new MockFirebaseService();
        }

        // Fail fast: outside explicit mock mode the service must never silently fall back to the
        // in-memory mock, because mock tokens would then authenticate against production data.
        String credentialsPath = properties.getCredentialsPath();
        if (credentialsPath == null || credentialsPath.trim().isEmpty()) {
            throw new IllegalStateException("Firebase credentials path is not configured. Set 'firebase.credentials-path' or enable 'firebase.mock-mode' for local development.");
        }
        if (properties.getWebApiKey() == null || properties.getWebApiKey().trim().isEmpty()) {
            throw new IllegalStateException("Firebase Web API Key is not configured. Set 'firebase.web-api-key' (FIREBASE_WEB_API_KEY); it is required for password sign-in and token issuance.");
        }

        Resource resource = resourceLoader.getResource(credentialsPath);
        if (!resource.exists()) {
            throw new IllegalStateException("Firebase credentials file not found at '" + credentialsPath + "'. Provide the service account file or enable 'firebase.mock-mode' for local development.");
        }

        try (InputStream serviceAccount = resource.getInputStream()) {
            FirebaseOptions options = FirebaseOptions.builder()
                    .setCredentials(GoogleCredentials.fromStream(serviceAccount))
                    .setHttpTransport(new com.google.api.client.http.javanet.NetHttpTransport())
                    .build();

            FirebaseApp firebaseApp;
            if (FirebaseApp.getApps().isEmpty()) {
                firebaseApp = FirebaseApp.initializeApp(options);
                log.info("FirebaseApp initialized successfully with credentials from '{}'.", credentialsPath);
            } else {
                firebaseApp = FirebaseApp.getInstance();
            }

            FirebaseAuth firebaseAuth = FirebaseAuth.getInstance(firebaseApp);
            return new FirebaseAuthService(firebaseAuth, properties.getWebApiKey());
        } catch (java.io.IOException e) {
            throw new IllegalStateException("Failed to initialize Firebase Admin SDK from path '" + credentialsPath + "': " + e.getMessage(), e);
        }
    }
}
