package com.hekma.identity.firebase;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "firebase")
@Getter
@Setter
public class FirebaseProperties {

    /**
     * Path to the Firebase service account JSON credentials file.
     * Can be a classpath resource (e.g. classpath:firebase-service-account.json)
     * or a filesystem path.
     */
    private String credentialsPath;

    /**
     * If true, uses an in-memory mock Firebase service suitable for testing
     * and local development without a Firebase project.
     */
    private boolean mockMode = false;

    /**
     * Firebase Web API Key (found in Firebase Console -> Project Settings -> General -> Web API Key).
     * Required for server-side token refreshing via Google Secure Token Service (STS).
     */
    private String webApiKey;
}
