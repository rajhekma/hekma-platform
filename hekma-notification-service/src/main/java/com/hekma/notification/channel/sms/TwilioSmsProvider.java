package com.hekma.notification.channel.sms;

import com.hekma.notification.channel.NotificationResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.notification.channels.sms.provider", havingValue = "twilio")
public class TwilioSmsProvider implements SmsProvider {

    private final String accountSid;
    private final String authToken;
    private final String fromNumber;
    private final HttpClient httpClient;

    public TwilioSmsProvider(
            @Value("${hekma.notification.channels.sms.twilio.account-sid:}") String accountSid,
            @Value("${hekma.notification.channels.sms.twilio.auth-token:}") String authToken,
            @Value("${hekma.notification.channels.sms.twilio.from-number:}") String fromNumber) {
        this.accountSid = accountSid;
        this.authToken = authToken;
        this.fromNumber = fromNumber;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    @Override
    public NotificationResult sendSms(String phoneNumber, String message) {
        if (accountSid == null || accountSid.isBlank() || authToken == null || authToken.isBlank()) {
            return NotificationResult.failure("Twilio account SID or auth token is missing");
        }

        try {
            String url = String.format("https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json", accountSid);
            Map<String, String> formData = Map.of(
                    "To", phoneNumber,
                    "From", fromNumber,
                    "Body", message
            );

            String formBody = formData.entrySet().stream()
                    .map(entry -> URLEncoder.encode(entry.getKey(), StandardCharsets.UTF_8) + "=" +
                            URLEncoder.encode(entry.getValue(), StandardCharsets.UTF_8))
                    .collect(Collectors.joining("&"));

            String authHeader = "Basic " + Base64.getEncoder().encodeToString((accountSid + ":" + authToken).getBytes(StandardCharsets.UTF_8));

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Authorization", authHeader)
                    .header("Content-Type", "application/x-www-form-urlencoded")
                    .POST(HttpRequest.BodyPublishers.ofString(formBody))
                    .timeout(Duration.ofSeconds(15))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                log.info("Twilio SMS sent to {} (status: {})", phoneNumber, response.statusCode());
                return NotificationResult.success("twilio-" + UUID.randomUUID());
            } else {
                log.error("Twilio SMS failed with HTTP {}: {}", response.statusCode(), response.body());
                return NotificationResult.failure("Twilio responded with error status: " + response.statusCode());
            }
        } catch (Exception ex) {
            log.error("Exception sending SMS via Twilio to {}: {}", phoneNumber, ex.getMessage(), ex);
            return NotificationResult.failure("SMS sending failed: " + ex.getMessage());
        }
    }
}
