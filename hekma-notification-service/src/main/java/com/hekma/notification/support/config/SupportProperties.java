package com.hekma.notification.support.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Data
@Configuration
@ConfigurationProperties(prefix = "hekma.support")
public class SupportProperties {

    private OtpProperties otp = new OtpProperties();
    private AttachmentProperties attachment = new AttachmentProperties();
    private SlaProperties sla = new SlaProperties();
    private JwtProperties jwt = new JwtProperties();

    @Data
    public static class OtpProperties {
        private String pepper = "hekma-otp-default-pepper-2026";
        private long ttlSeconds = 600;
        private int maxAttempts = 5;
        private long lockTtlSeconds = 1800;
        private long resendCooldownSeconds = 60;
        private long sessionTtlSeconds = 1800;
    }

    @Data
    public static class AttachmentProperties {
        private long maxSizeBytes = 10485760; // 10MB
        private int maxCount = 5;
        private String storageProvider = "mock";
        private S3Properties s3 = new S3Properties();

        @Data
        public static class S3Properties {
            private String bucket = "hekma-support-attachments";
            private String region = "us-east-1";
            private String baseUrl = "https://hekma-support-attachments.s3.amazonaws.com";
        }
    }

    @Data
    public static class SlaProperties {
        private int defaultHours = 24;
    }

    @Data
    public static class JwtProperties {
        private String secret = "Graphql";
    }
}
