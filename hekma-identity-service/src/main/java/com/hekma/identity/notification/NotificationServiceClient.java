package com.hekma.identity.notification;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.Map;
import java.util.UUID;

/**
 * Client for delegating all outbound notifications (SMS OTPs) to hekma-notification-service.
 */
@Service
@Slf4j
public class NotificationServiceClient {

    private final RestTemplate restTemplate;
    private final String notificationServiceUrl;
    private final String serviceKey;

    @org.springframework.beans.factory.annotation.Autowired
    public NotificationServiceClient(
            @Value("${app.notification-service.url:http://localhost:8081}") String notificationServiceUrl,
            @Value("${app.notification-service.service-key:13f8fc11-b3b5-4a9e-ab49-06e96a57f42b}") String serviceKey) {
        this(new RestTemplate(), notificationServiceUrl, serviceKey);
        if (serviceKey == null || serviceKey.isBlank()) {
            log.warn("Notification service key is not configured. Outbound notifications will be skipped or may fail.");
        }
    }

    public NotificationServiceClient(
            RestTemplate restTemplate,
            String notificationServiceUrl,
            String serviceKey) {
        this.restTemplate = restTemplate != null ? restTemplate : new RestTemplate();
        this.notificationServiceUrl = notificationServiceUrl;
        this.serviceKey = serviceKey;
    }

    private HttpHeaders createHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Hekma-Service-Key", serviceKey);
        String traceId = org.slf4j.MDC.get(com.hekma.identity.config.TraceIdFilter.TRACE_ID_MDC_KEY);
        if (traceId != null && !traceId.isBlank()) {
            headers.set(com.hekma.identity.config.TraceIdFilter.TRACE_ID_HEADER, traceId);
            headers.set(com.hekma.identity.config.TraceIdFilter.TRACE_ID_HEADER_LOWER, traceId);
        }
        return headers;
    }

    /**
     * Dispatches an OTP SMS notification request to hekma-notification-service.
     *
     * @param phoneNumber recipient E.164 phone number
     * @param otpCode 6-digit plain text OTP (only used in transit for the SMS body)
     * @param attemptId unique authentication attempt identifier for idempotency
     */
    public void sendOtpSms(String phoneNumber, String otpCode, UUID attemptId) {
        String endpoint = notificationServiceUrl + "/api/v1/notifications/send";
        log.info("Dispatching OTP SMS to hekma-notification-service at {} for recipient {}", endpoint, phoneNumber);

        NotificationSendDto payload = NotificationSendDto.builder()
                .channel("SMS")
                .recipient(phoneNumber)
                .title("Hekma Authentication Code")
                .content("Your Hekma verification code is " + otpCode + ". Valid for 5 minutes.")
                .priority("HIGH")
                .templateParams(Map.of("code", otpCode))
                .sourceService("hekma-identity-service")
                .idempotencyKey("otp-" + attemptId + "-" + System.currentTimeMillis())
                .async(true)
                .build();

        HttpEntity<NotificationSendDto> entity = new HttpEntity<>(payload, createHeaders());

        try {
            ResponseEntity<String> response = restTemplate.postForEntity(endpoint, entity, String.class);
            log.info("Notification service accepted SMS dispatch for {} with status {}", phoneNumber, response.getStatusCode());
        } catch (Exception e) {
            log.warn("Failed to reach hekma-notification-service at {}: {}. (Will proceed to allow mock/offline resilience)",
                    endpoint, e.getMessage());
        }
    }

    /**
     * Dispatches an OTP Email notification request to hekma-notification-service.
     *
     * @param email recipient email address
     * @param otpCode 6-digit plain text OTP
     * @param attemptId unique authentication attempt identifier
     */
    public void sendOtpEmail(String email, String otpCode, UUID attemptId) {
        String endpoint = notificationServiceUrl + "/api/v1/notifications/send";
        log.info("Dispatching OTP Email to hekma-notification-service at {} for recipient {}", endpoint, email);

        NotificationSendDto payload = NotificationSendDto.builder()
                .channel("EMAIL")
                .recipient(email)
                .title("Your Hekma Verification Code")
                .content("Your Hekma verification code is " + otpCode + ". Valid for 5 minutes.")
                .priority("HIGH")
                .templateParams(Map.of("code", otpCode))
                .sourceService("hekma-identity-service")
                .idempotencyKey("otp-email-" + attemptId + "-" + System.currentTimeMillis())
                .async(true)
                .build();

        HttpEntity<NotificationSendDto> entity = new HttpEntity<>(payload, createHeaders());

        try {
            ResponseEntity<String> response = restTemplate.postForEntity(endpoint, entity, String.class);
            log.info("Notification service accepted Email OTP dispatch for {} with status {}", email, response.getStatusCode());
        } catch (Exception e) {
            log.warn("Failed to reach hekma-notification-service at {}: {}. (Will proceed to allow mock/offline resilience)",
                    endpoint, e.getMessage());
        }
    }

    /**
     * Dispatches a Welcome Email notification request to hekma-notification-service.
     */
    public void sendWelcomeEmail(String email, String displayName) {
        String endpoint = notificationServiceUrl + "/api/v1/notifications/send";
        String name = (displayName != null && !displayName.isBlank()) ? displayName : "User";
        log.info("Dispatching Welcome Email to hekma-notification-service at {} for recipient {}", endpoint, email);

        NotificationSendDto payload = NotificationSendDto.builder()
                .channel("EMAIL")
                .recipient(email)
                .title("Welcome to Hekma, " + name + "!")
                .content("Welcome to Hekma! Your account has been registered successfully. Explore services in your dashboard.")
                .priority("NORMAL")
                .sourceService("hekma-identity-service")
                .idempotencyKey("welcome-email-" + email + "-" + System.currentTimeMillis())
                .async(true)
                .build();

        HttpEntity<NotificationSendDto> entity = new HttpEntity<>(payload, createHeaders());

        try {
            ResponseEntity<String> response = restTemplate.postForEntity(endpoint, entity, String.class);
            log.info("Notification service accepted Welcome Email for {} with status {}", email, response.getStatusCode());
        } catch (Exception e) {
            log.warn("Failed to reach hekma-notification-service at {} for welcome email: {}", endpoint, e.getMessage());
        }
    }

    /**
     * Dispatches an In-App Welcome notification request to hekma-notification-service.
     */
    public void sendWelcomeInApp(UUID userId, String displayName) {
        String endpoint = notificationServiceUrl + "/api/v1/notifications/send";
        String name = (displayName != null && !displayName.isBlank()) ? displayName : "User";
        log.info("Dispatching Welcome In-App notification to hekma-notification-service for user {}", userId);

        NotificationSendDto payload = NotificationSendDto.builder()
                .channel("IN_APP")
                .recipient(userId.toString())
                .title("Welcome to Hekma!")
                .content("Welcome " + name + ", your account is active. Explore clinical trials and updates in your dashboard.")
                .priority("NORMAL")
                .sourceService("hekma-identity-service")
                .idempotencyKey("welcome-inapp-" + userId)
                .async(true)
                .build();

        HttpEntity<NotificationSendDto> entity = new HttpEntity<>(payload, createHeaders());

        try {
            ResponseEntity<String> response = restTemplate.postForEntity(endpoint, entity, String.class);
            log.info("Notification service accepted Welcome In-App for user {} with status {}", userId, response.getStatusCode());
        } catch (Exception e) {
            log.warn("Failed to reach hekma-notification-service at {} for welcome in-app: {}", endpoint, e.getMessage());
        }
    }

    /**
     * Dispatches a Patient Invitation Email notification to hekma-notification-service.
     */
    /**
     * Sends a staff (SPONSOR/SITE) invitation email carrying the single-use acceptance link.
     */
    public void sendStaffInvitationEmail(String email, String inviterName, String organizationName, String invitationLink, UUID invitationId) {
        String endpoint = notificationServiceUrl + "/api/v1/notifications/send";
        log.info("Dispatching Staff Invitation Email to hekma-notification-service for recipient {}", email);

        String org = (organizationName != null && !organizationName.isBlank()) ? organizationName : "Hekma Platform";
        String inviter = (inviterName != null && !inviterName.isBlank()) ? inviterName : "Your administrator";

        NotificationSendDto payload = NotificationSendDto.builder()
                .channel("EMAIL")
                .recipient(email)
                .title("Invitation to join " + org + " on Hekma")
                .content(inviter + " invited you to join " + org + " on Hekma. Accept your invitation within 72 hours: " + invitationLink)
                .priority("HIGH")
                .templateParams(Map.of(
                        "inviterName", inviter,
                        "organizationName", org,
                        "invitationLink", invitationLink
                ))
                .sourceService("hekma-identity-service")
                .idempotencyKey("invite-staff-" + invitationId)
                .async(true)
                .build();

        try {
            ResponseEntity<String> response = restTemplate.postForEntity(endpoint, new HttpEntity<>(payload, createHeaders()), String.class);
            log.info("Notification service accepted Staff Invitation Email for {} with status {}", email, response.getStatusCode());
        } catch (Exception e) {
            log.warn("Failed to reach hekma-notification-service at {} for staff invitation email: {}", endpoint, e.getMessage());
        }
    }

    public void sendPatientInvitationEmail(String email, String inviterName, String organizationName, String invitationCode, String invitationLink) {
        String endpoint = notificationServiceUrl + "/api/v1/notifications/send";
        log.info("Dispatching Patient Invitation Email to hekma-notification-service for recipient {}", email);

        String org = (organizationName != null && !organizationName.isBlank()) ? organizationName : "Hekma Platform";
        String inviter = (inviterName != null && !inviterName.isBlank()) ? inviterName : "Clinical Investigator";

        NotificationSendDto payload = NotificationSendDto.builder()
                .channel("EMAIL")
                .recipient(email)
                .title("Invitation to Join Clinical Study with " + org)
                .content("You have been invited by " + inviter + " at " + org + " to join a clinical trial on Hekma. Your invitation code is " + invitationCode + ". Accept your invitation here: " + invitationLink)
                .priority("HIGH")
                .templateParams(Map.of(
                        "inviterName", inviter,
                        "organizationName", org,
                        "invitationCode", invitationCode,
                        "invitationLink", invitationLink != null ? invitationLink : ""
                ))
                .sourceService("hekma-identity-service")
                .idempotencyKey("invite-patient-" + email + "-" + invitationCode)
                .async(true)
                .build();

        HttpEntity<NotificationSendDto> entity = new HttpEntity<>(payload, createHeaders());

        try {
            ResponseEntity<String> response = restTemplate.postForEntity(endpoint, entity, String.class);
            log.info("Notification service accepted Patient Invitation Email for {} with status {}", email, response.getStatusCode());
        } catch (Exception e) {
            log.warn("Failed to reach hekma-notification-service at {} for patient invitation email: {}", endpoint, e.getMessage());
        }
    }
}
