package com.hekma.notification.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.notification.config.ApiKeyAuthFilter;
import com.hekma.notification.config.GlobalExceptionHandler;
import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationStatus;
import com.hekma.notification.dto.BroadcastNotificationRequest;
import com.hekma.notification.dto.BroadcastNotificationResponse;
import com.hekma.notification.dto.NotificationResponse;
import com.hekma.notification.dto.NotificationSendRequest;
import com.hekma.notification.service.NotificationDispatcherService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class NotificationControllerIntegrationTest {

    private MockMvc mockMvc;

    @Mock
    private NotificationDispatcherService dispatcherService;

    @InjectMocks
    private NotificationController notificationController;

    private ObjectMapper objectMapper;

    private static final String API_KEY_HEADER = "X-Hekma-Service-Key";
    private static final String VALID_KEY = "test-internal-service-key";

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(notificationController)
                .addFilters(new ApiKeyAuthFilter(VALID_KEY))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
    }

    @Test
    void testSendNotification_WithoutApiKey_ShouldReturnUnauthorized() throws Exception {
        NotificationSendRequest request = NotificationSendRequest.builder()
                .channel(NotificationChannel.EMAIL)
                .recipient("test@hekma.com")
                .content("Test content")
                .build();

        mockMvc.perform(post("/api/v1/notifications/send")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void testSendNotification_WithValidApiKey_ShouldReturnAccepted() throws Exception {
        NotificationSendRequest request = NotificationSendRequest.builder()
                .channel(NotificationChannel.EMAIL)
                .recipient("test@hekma.com")
                .title("Welcome")
                .content("Your account is ready")
                .build();

        UUID logId = UUID.randomUUID();
        NotificationResponse response = NotificationResponse.builder()
                .id(logId)
                .channel(NotificationChannel.EMAIL)
                .recipient("test@hekma.com")
                .status(NotificationStatus.PENDING)
                .createdAt(Instant.now())
                .build();

        when(dispatcherService.sendNotification(any(NotificationSendRequest.class))).thenReturn(response);

        mockMvc.perform(post("/api/v1/notifications/send")
                        .header(API_KEY_HEADER, VALID_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.id").value(logId.toString()))
                .andExpect(jsonPath("$.channel").value("EMAIL"))
                .andExpect(jsonPath("$.recipient").value("test@hekma.com"));
    }

    @Test
    void testBroadcastNotification_WithValidApiKey_ShouldReturnOk() throws Exception {
        BroadcastNotificationRequest request = BroadcastNotificationRequest.builder()
                .channels(List.of(NotificationChannel.EMAIL, NotificationChannel.IN_APP))
                .email("doctor@hekma.com")
                .userId("usr_123")
                .title("Alert")
                .content("New Emergency Notification")
                .build();

        BroadcastNotificationResponse response = BroadcastNotificationResponse.builder()
                .totalDispatched(2)
                .results(List.of(
                        NotificationResponse.builder()
                                .id(UUID.randomUUID())
                                .channel(NotificationChannel.EMAIL)
                                .recipient("doctor@hekma.com")
                                .status(NotificationStatus.PENDING)
                                .build(),
                        NotificationResponse.builder()
                                .id(UUID.randomUUID())
                                .channel(NotificationChannel.IN_APP)
                                .recipient("usr_123")
                                .status(NotificationStatus.SENT)
                                .build()
                ))
                .build();

        when(dispatcherService.broadcast(any(BroadcastNotificationRequest.class))).thenReturn(response);

        mockMvc.perform(post("/api/v1/notifications/broadcast")
                        .header(API_KEY_HEADER, VALID_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalDispatched").value(2))
                .andExpect(jsonPath("$.results[0].channel").value("EMAIL"))
                .andExpect(jsonPath("$.results[1].channel").value("IN_APP"));
    }

    @Test
    void testGetNotificationStatus_WithValidApiKey_ShouldReturnOk() throws Exception {
        UUID id = UUID.randomUUID();
        NotificationResponse response = NotificationResponse.builder()
                .id(id)
                .channel(NotificationChannel.SMS)
                .recipient("+966500000000")
                .status(NotificationStatus.DELIVERED)
                .build();

        when(dispatcherService.getStatus(id)).thenReturn(response);

        mockMvc.perform(get("/api/v1/notifications/" + id + "/status")
                        .header(API_KEY_HEADER, VALID_KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id.toString()))
                .andExpect(jsonPath("$.status").value("DELIVERED"));
    }
}
