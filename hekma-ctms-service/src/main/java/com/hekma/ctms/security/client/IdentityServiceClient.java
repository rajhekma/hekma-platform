package com.hekma.ctms.security.client;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Slf4j
@Component
public class IdentityServiceClient {

    private final RestClient restClient;
    private final String serviceKey;
    private final long cacheTtlSeconds;

    private record CacheEntry(TokenIntrospectResponse response, Instant expiresAt) {
        boolean isExpired() {
            return Instant.now().isAfter(expiresAt);
        }
    }

    private final Map<String, CacheEntry> tokenCache = new ConcurrentHashMap<>();

    public IdentityServiceClient(
            @Value("${app.identity-service.url:http://localhost:8080}") String identityUrl,
            @Value("${app.identity-service.service-key:13f8fc11-b3b5-4a9e-ab49-06e96a57f42b}") String serviceKey,
            @Value("${app.identity-service.cache-ttl-seconds:60}") long cacheTtlSeconds) {
        this.serviceKey = serviceKey;
        this.cacheTtlSeconds = cacheTtlSeconds;
        this.restClient = RestClient.builder()
                .baseUrl(identityUrl)
                .build();
    }

    public TokenIntrospectResponse introspect(String token) {
        if (token == null || token.isBlank()) {
            return TokenIntrospectResponse.inactive();
        }

        String hash = hashToken(token);
        CacheEntry cached = tokenCache.get(hash);
        if (cached != null && !cached.isExpired()) {
            return cached.response();
        }

        try {
            String traceId = org.slf4j.MDC.get(com.hekma.ctms.config.TraceIdFilter.TRACE_ID_MDC_KEY);
            var requestSpec = restClient.post()
                    .uri("/internal/v1/auth/introspect")
                    .header("X-Hekma-Service-Key", serviceKey)
                    .contentType(MediaType.APPLICATION_JSON);
            if (traceId != null && !traceId.isBlank()) {
                requestSpec = requestSpec.header(com.hekma.ctms.config.TraceIdFilter.TRACE_ID_HEADER, traceId)
                        .header(com.hekma.ctms.config.TraceIdFilter.TRACE_ID_HEADER_LOWER, traceId);
            }
            TokenIntrospectResponse response = requestSpec
                    .body(new TokenIntrospectRequest(token))
                    .retrieve()
                    .body(TokenIntrospectResponse.class);

            if (response != null && response.active()) {
                tokenCache.put(hash, new CacheEntry(response, Instant.now().plusSeconds(cacheTtlSeconds)));
                return response;
            }
            return TokenIntrospectResponse.inactive();
        } catch (Exception e) {
            log.error("Failed to introspect token against identity service: {}", e.getMessage());
            return TokenIntrospectResponse.inactive();
        }
    }

    private String hashToken(String token) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(token.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
