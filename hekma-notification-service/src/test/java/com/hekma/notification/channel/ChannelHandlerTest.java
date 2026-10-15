package com.hekma.notification.channel;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.notification.channel.email.EmailChannelHandler;
import com.hekma.notification.channel.email.MockEmailProvider;
import com.hekma.notification.channel.inapp.InAppChannelHandler;
import com.hekma.notification.channel.push.MockPushProvider;
import com.hekma.notification.channel.push.PushChannelHandler;
import com.hekma.notification.channel.sms.MockSmsProvider;
import com.hekma.notification.channel.sms.SmsChannelHandler;
import com.hekma.notification.domain.entity.InAppNotification;
import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.repository.InAppNotificationRepository;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

class ChannelHandlerTest {

    @Test
    void testEmailChannelHandler() {
        MockEmailProvider provider = new MockEmailProvider();
        EmailChannelHandler handler = new EmailChannelHandler(provider, "no-reply@hekma.com");

        assertEquals(NotificationChannel.EMAIL, handler.getChannel());

        ChannelDispatchContext context = ChannelDispatchContext.builder()
                .logId(UUID.randomUUID())
                .channel(NotificationChannel.EMAIL)
                .recipient("test@hekma.com")
                .title("Welcome")
                .content("Welcome to Hekma!")
                .build();

        NotificationResult result = handler.handle(context);
        assertTrue(result.isSuccess());
        assertNotNull(result.getProviderMessageId());
        assertTrue(result.getProviderMessageId().startsWith("mock-email-"));
    }

    @Test
    void testSmsChannelHandler() {
        MockSmsProvider provider = new MockSmsProvider();
        SmsChannelHandler handler = new SmsChannelHandler(provider);

        assertEquals(NotificationChannel.SMS, handler.getChannel());

        ChannelDispatchContext context = ChannelDispatchContext.builder()
                .logId(UUID.randomUUID())
                .channel(NotificationChannel.SMS)
                .recipient("+966500000000")
                .title("OTP")
                .content("Your verification code is 1234")
                .build();

        NotificationResult result = handler.handle(context);
        assertTrue(result.isSuccess());
        assertNotNull(result.getProviderMessageId());
        assertTrue(result.getProviderMessageId().startsWith("mock-sms-"));
    }

    @Test
    void testPushChannelHandler() {
        MockPushProvider provider = new MockPushProvider();
        PushChannelHandler handler = new PushChannelHandler(provider);

        assertEquals(NotificationChannel.PUSH, handler.getChannel());

        ChannelDispatchContext context = ChannelDispatchContext.builder()
                .logId(UUID.randomUUID())
                .channel(NotificationChannel.PUSH)
                .recipient("fcm-device-token-123")
                .title("New Message")
                .content("You have received a new consultation message")
                .metadata(Map.of("chatId", "c-456"))
                .build();

        NotificationResult result = handler.handle(context);
        assertTrue(result.isSuccess());
        assertNotNull(result.getProviderMessageId());
        assertTrue(result.getProviderMessageId().startsWith("mock-push-"));
    }

    @Test
    void testInAppChannelHandler() {
        InAppNotificationRepository repository = Mockito.mock(InAppNotificationRepository.class);
        ObjectMapper objectMapper = new ObjectMapper();
        InAppChannelHandler handler = new InAppChannelHandler(repository, objectMapper);

        assertEquals(NotificationChannel.IN_APP, handler.getChannel());

        UUID generatedId = UUID.randomUUID();
        when(repository.save(any(InAppNotification.class))).thenAnswer(invocation -> {
            InAppNotification n = invocation.getArgument(0);
            n.setId(generatedId);
            return n;
        });

        ChannelDispatchContext context = ChannelDispatchContext.builder()
                .logId(UUID.randomUUID())
                .channel(NotificationChannel.IN_APP)
                .recipient("usr_7788")
                .title("Appointment Confirmed")
                .content("Dr. Smith confirmed your booking.")
                .metadata(Map.of("category", "APPOINTMENT", "actionUrl", "/appointments/123"))
                .build();

        NotificationResult result = handler.handle(context);
        assertTrue(result.isSuccess());
        assertEquals(generatedId.toString(), result.getProviderMessageId());
    }
}
