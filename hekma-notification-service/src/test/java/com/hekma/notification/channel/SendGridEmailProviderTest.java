package com.hekma.notification.channel;

import com.hekma.notification.channel.email.SendGridEmailProvider;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

class SendGridEmailProviderTest {

    @Test
    void testSendEmail_Success() {
        RestTemplate restTemplate = Mockito.mock(RestTemplate.class);
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Message-Id", "sg-msg-12345");
        ResponseEntity<String> response = new ResponseEntity<>("", headers, HttpStatus.ACCEPTED);

        when(restTemplate.postForEntity(eq("https://api.sendgrid.com/v3/mail/send"), any(HttpEntity.class), eq(String.class)))
                .thenReturn(response);

        SendGridEmailProvider provider = new SendGridEmailProvider(restTemplate, "SG.test-api-key");
        NotificationResult result = provider.sendEmail("recipient@mailinator.com", "OTP Code", "Your OTP is 123456", "support@hekma.ai");

        assertTrue(result.isSuccess());
        assertEquals("sg-msg-12345", result.getProviderMessageId());
    }

    @Test
    void testSendEmail_NoApiKey_FallsBackToConsole() {
        RestTemplate restTemplate = Mockito.mock(RestTemplate.class);
        SendGridEmailProvider provider = new SendGridEmailProvider(restTemplate, "");

        NotificationResult result = provider.sendEmail("recipient@mailinator.com", "OTP Code", "Your OTP is 123456", "support@hekma.ai");

        assertTrue(result.isSuccess());
        assertTrue(result.getProviderMessageId().startsWith("mock-sg-"));
    }

    @Test
    void testSendEmail_ApiRejection_ReturnsFailure() {
        RestTemplate restTemplate = Mockito.mock(RestTemplate.class);
        ResponseEntity<String> response = new ResponseEntity<>("{\"errors\":[]}", HttpStatus.UNAUTHORIZED);

        when(restTemplate.postForEntity(eq("https://api.sendgrid.com/v3/mail/send"), any(HttpEntity.class), eq(String.class)))
                .thenReturn(response);

        SendGridEmailProvider provider = new SendGridEmailProvider(restTemplate, "SG.test-api-key");
        NotificationResult result = provider.sendEmail("recipient@mailinator.com", "OTP Code", "Your OTP is 123456", "support@hekma.ai");

        assertFalse(result.isSuccess());
        assertTrue(result.getErrorMessage().contains("rejected"));
    }
}
