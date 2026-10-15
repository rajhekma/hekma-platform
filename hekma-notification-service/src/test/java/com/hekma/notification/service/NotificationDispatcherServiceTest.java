package com.hekma.notification.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.notification.channel.ChannelDispatchContext;
import com.hekma.notification.channel.NotificationChannelHandler;
import com.hekma.notification.channel.NotificationChannelRegistry;
import com.hekma.notification.channel.NotificationResult;
import com.hekma.notification.domain.entity.NotificationLog;
import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationStatus;
import com.hekma.notification.domain.repository.NotificationLogRepository;
import com.hekma.notification.dto.BroadcastNotificationRequest;
import com.hekma.notification.dto.BroadcastNotificationResponse;
import com.hekma.notification.dto.NotificationResponse;
import com.hekma.notification.dto.NotificationSendRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class NotificationDispatcherServiceTest {

    @Mock
    private NotificationChannelRegistry channelRegistry;

    @Mock
    private NotificationLogRepository notificationLogRepository;

    @Mock
    private NotificationAsyncDispatcher asyncDispatcher;

    @Mock
    private NotificationChannelHandler emailHandler;

    @Mock
    private NotificationChannelHandler smsHandler;

    private NotificationDispatcherService dispatcherService;

    @BeforeEach
    void setUp() {
        TemplateRenderer templateRenderer = new TemplateRenderer();
        ObjectMapper objectMapper = new ObjectMapper();
        dispatcherService = new NotificationDispatcherService(
                channelRegistry,
                notificationLogRepository,
                asyncDispatcher,
                templateRenderer,
                objectMapper
        );
    }

    @Test
    void testSendNotification_SyncSuccess() {
        when(channelRegistry.getHandler(NotificationChannel.EMAIL)).thenReturn(Optional.of(emailHandler));
        when(emailHandler.handle(any(ChannelDispatchContext.class))).thenReturn(NotificationResult.success("email-123"));

        UUID generatedId = UUID.randomUUID();
        when(notificationLogRepository.save(any(NotificationLog.class))).thenAnswer(invocation -> {
            NotificationLog log = invocation.getArgument(0);
            if (log.getId() == null) {
                log.setId(generatedId);
            }
            return log;
        });

        NotificationSendRequest request = NotificationSendRequest.builder()
                .channel(NotificationChannel.EMAIL)
                .recipient("patient@hekma.com")
                .title("Welcome {{name}}")
                .content("Your activation code is {{code}}")
                .templateParams(Map.of("name", "John", "code", "9876"))
                .async(false)
                .build();

        NotificationResponse response = dispatcherService.sendNotification(request);

        assertNotNull(response);
        assertEquals(NotificationStatus.SENT, response.getStatus());
        assertEquals("email-123", response.getProviderMessageId());
        assertEquals(NotificationChannel.EMAIL, response.getChannel());
        verify(emailHandler, times(1)).handle(any(ChannelDispatchContext.class));
    }

    @Test
    void testSendNotification_Idempotency() {
        String idempotencyKey = "unique-key-123";
        NotificationLog existingLog = NotificationLog.builder()
                .id(UUID.randomUUID())
                .channel(NotificationChannel.SMS)
                .recipient("+966500000000")
                .status(NotificationStatus.SENT)
                .idempotencyKey(idempotencyKey)
                .content("Code 123")
                .build();

        when(notificationLogRepository.findByIdempotencyKey(idempotencyKey)).thenReturn(Optional.of(existingLog));

        NotificationSendRequest request = NotificationSendRequest.builder()
                .channel(NotificationChannel.SMS)
                .recipient("+966500000000")
                .content("Code 123")
                .idempotencyKey(idempotencyKey)
                .build();

        NotificationResponse response = dispatcherService.sendNotification(request);

        assertNotNull(response);
        assertEquals(existingLog.getId(), response.getId());
        verify(channelRegistry, never()).getHandler(any());
    }

    @Test
    void testBroadcastNotification() {
        when(channelRegistry.getHandler(NotificationChannel.EMAIL)).thenReturn(Optional.of(emailHandler));
        when(channelRegistry.getHandler(NotificationChannel.SMS)).thenReturn(Optional.of(smsHandler));

        when(notificationLogRepository.save(any(NotificationLog.class))).thenAnswer(invocation -> {
            NotificationLog log = invocation.getArgument(0);
            if (log.getId() == null) {
                log.setId(UUID.randomUUID());
            }
            return log;
        });

        BroadcastNotificationRequest request = BroadcastNotificationRequest.builder()
                .channels(List.of(NotificationChannel.EMAIL, NotificationChannel.SMS))
                .email("user@hekma.com")
                .phone("+966500000000")
                .title("Alert")
                .content("Broadcasting message")
                .build();

        BroadcastNotificationResponse broadcastResponse = dispatcherService.broadcast(request);

        assertNotNull(broadcastResponse);
        assertEquals(2, broadcastResponse.getTotalDispatched());
        assertEquals(2, broadcastResponse.getResults().size());
    }
}
