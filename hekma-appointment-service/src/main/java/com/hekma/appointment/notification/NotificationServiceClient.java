package com.hekma.appointment.notification;

import com.hekma.appointment.config.TraceIdFilter;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

@Service
@Slf4j
public class NotificationServiceClient {

    private final RestClient restClient;
    private final String serviceKey;

    public NotificationServiceClient(
            @Value("${app.notification-service.url:http://localhost:8081}") String notificationUrl,
            @Value("${app.notification-service.service-key:13f8fc11-b3b5-4a9e-ab49-06e96a57f42b}") String serviceKey) {
        this.serviceKey = serviceKey;
        this.restClient = RestClient.builder()
                .baseUrl(notificationUrl)
                .build();
    }

    public void sendAppointmentEmail(String recipientEmail, String subject, String content, String appointmentId, String actionType) {
        if (recipientEmail == null || recipientEmail.isBlank()) {
            log.debug("Skipping email notification: no recipient email provided");
            return;
        }

        try {
            Map<String, Object> payload = new HashMap<>();
            payload.put("channel", "EMAIL");
            payload.put("recipient", recipientEmail);
            payload.put("title", subject);
            payload.put("content", content);
            payload.put("sourceService", "hekma-appointment-service");
            payload.put("idempotencyKey", "appt-email-" + appointmentId + "-" + actionType + "-" + UUID.randomUUID());
            payload.put("async", true);

            Map<String, Object> metadata = new HashMap<>();
            metadata.put("appointmentId", appointmentId);
            metadata.put("actionType", actionType);
            payload.put("metadata", metadata);

            executePost("/api/v1/notifications/send", payload);
            log.info("Dispatched appointment email ({}) to {} for appt {}", actionType, recipientEmail, appointmentId);
        } catch (Exception e) {
            log.error("Failed to send appointment email to {}: {}", recipientEmail, e.getMessage());
        }
    }

    public void sendAppointmentPush(String recipientId, String title, String content, String appointmentId, String actionType) {
        if (recipientId == null || recipientId.isBlank()) {
            log.debug("Skipping push notification: no recipient user ID provided");
            return;
        }

        try {
            Map<String, Object> payload = new HashMap<>();
            payload.put("channel", "PUSH");
            payload.put("recipient", recipientId);
            payload.put("title", title);
            payload.put("content", content);
            payload.put("sourceService", "hekma-appointment-service");
            payload.put("idempotencyKey", "appt-push-" + appointmentId + "-" + actionType + "-" + UUID.randomUUID());
            payload.put("async", true);

            Map<String, Object> metadata = new HashMap<>();
            metadata.put("appointmentId", appointmentId);
            metadata.put("actionType", actionType);
            payload.put("metadata", metadata);

            executePost("/api/v1/notifications/send", payload);
            log.info("Dispatched appointment push ({}) to user {} for appt {}", actionType, recipientId, appointmentId);
        } catch (Exception e) {
            log.error("Failed to send appointment push to {}: {}", recipientId, e.getMessage());
        }
    }

    private void executePost(String uri, Map<String, Object> payload) {
        String traceId = MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY);
        var requestSpec = restClient.post()
                .uri(uri)
                .header("X-Hekma-Service-Key", serviceKey)
                .contentType(MediaType.APPLICATION_JSON);

        if (traceId != null && !traceId.isBlank()) {
            requestSpec = requestSpec.header(TraceIdFilter.TRACE_ID_HEADER, traceId)
                    .header(TraceIdFilter.TRACE_ID_HEADER_LOWER, traceId);
        }

        requestSpec.body(payload).retrieve().toBodilessEntity();
    }
}
