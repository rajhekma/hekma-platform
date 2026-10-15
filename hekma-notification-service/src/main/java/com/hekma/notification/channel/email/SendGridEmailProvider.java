package com.hekma.notification.channel.email;

import com.hekma.notification.channel.NotificationResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.notification.channels.email.provider", havingValue = "sendgrid")
public class SendGridEmailProvider implements EmailProvider {

    private static final String SENDGRID_ENDPOINT = "https://api.sendgrid.com/v3/mail/send";

    private final RestTemplate restTemplate;
    private final String apiKey;

    @Autowired
    public SendGridEmailProvider(
            @Value("${hekma.notification.channels.email.sendgrid.api-key:${spring.sendgrid.api-key:}}") String apiKey) {
        this(new RestTemplate(), apiKey);
    }

    public SendGridEmailProvider(RestTemplate restTemplate, String apiKey) {
        this.restTemplate = restTemplate != null ? restTemplate : new RestTemplate();
        this.apiKey = apiKey != null ? apiKey.trim() : "";
    }

    @Override
    public NotificationResult sendEmail(String to, String subject, String body, String from) {
        if (apiKey.isEmpty()) {
            String fallbackId = "mock-sg-" + UUID.randomUUID();
            log.warn("[SENDGRID WARNING] API key is not configured. Falling back to console preview.");
            printConsoleFallback(to, subject, body, from);
            return NotificationResult.success(fallbackId);
        }

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.setBearerAuth(apiKey);

            Map<String, Object> payload = buildPayload(to, subject, body, from);
            HttpEntity<Map<String, Object>> request = new HttpEntity<>(payload, headers);

            ResponseEntity<String> response = restTemplate.postForEntity(SENDGRID_ENDPOINT, request, String.class);

            if (response.getStatusCode().is2xxSuccessful()) {
                String messageId = response.getHeaders().getFirst("X-Message-Id");
                if (messageId == null || messageId.isBlank()) {
                    messageId = "sg-" + UUID.randomUUID();
                }
                log.info("Email sent successfully via SendGrid to {} (status={}, messageId={})", to, response.getStatusCode(), messageId);
                System.out.println("==================================================================");
                System.out.println(">>> [EMAIL SENT VIA SENDGRID API] <<<");
                System.out.println(">>> From: " + from);
                System.out.println(">>> To: " + to);
                System.out.println(">>> Subject: " + subject);
                System.out.println(">>> SendGrid Message-ID: " + messageId);
                System.out.println("==================================================================");
                return NotificationResult.success(messageId);
            } else {
                log.error("SendGrid rejected email to {}: status={}, body={}", to, response.getStatusCode(), response.getBody());
                printConsoleFallback(to, subject, body, from);
                return NotificationResult.failure("SendGrid rejected email with status " + response.getStatusCode());
            }
        } catch (Exception ex) {
            log.error("Failed to send email via SendGrid to {}: {}", to, ex.getMessage(), ex);
            printConsoleFallback(to, subject, body, from);
            return NotificationResult.failure("SendGrid delivery failed: " + ex.getMessage());
        }
    }

    private void printConsoleFallback(String to, String subject, String body, String from) {
        System.out.println("==================================================================");
        System.out.println(">>> [SENDGRID DISPATCH PREVIEW - CONSOLE FALLBACK] <<<");
        System.out.println(">>> From: " + from);
        System.out.println(">>> To: " + to);
        System.out.println(">>> Subject: " + subject);
        System.out.println(">>> Content: " + body);
        System.out.println("==================================================================");
    }

    private Map<String, Object> buildPayload(String to, String subject, String body, String from) {
        Map<String, Object> payload = new HashMap<>();

        Map<String, Object> toRecipient = Map.of("email", to.trim());
        Map<String, Object> personalization = Map.of("to", List.of(toRecipient));
        payload.put("personalizations", List.of(personalization));

        Map<String, Object> fromObj = Map.of(
                "email", (from != null && !from.isBlank()) ? from.trim() : "support@hekma.ai",
                "name", "Hekma Platform"
        );
        payload.put("from", fromObj);

        payload.put("subject", subject != null ? subject : "Hekma Notification");

        String htmlContent = body;
        if (!body.contains("<html") && !body.contains("<p")) {
            htmlContent = "<div style=\"font-family: sans-serif; font-size: 14px; color: #333;\"><p>" + body + "</p></div>";
        }

        Map<String, Object> contentObj = Map.of(
                "type", "text/html",
                "value", htmlContent
        );
        payload.put("content", List.of(contentObj));

        return payload;
    }
}
