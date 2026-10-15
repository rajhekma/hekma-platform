package com.hekma.notification.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.notification.config.GlobalExceptionHandler;
import com.hekma.notification.dto.InAppNotificationDto;
import com.hekma.notification.dto.UnreadCountDto;
import com.hekma.notification.service.InAppNotificationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableHandlerMethodArgumentResolver;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class InAppNotificationControllerTest {

    private MockMvc mockMvc;

    @Mock
    private InAppNotificationService inAppService;

    @InjectMocks
    private InAppNotificationController inAppController;

    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(inAppController)
                .setCustomArgumentResolvers(new PageableHandlerMethodArgumentResolver())
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
    }

    @Test
    void testGetUserNotifications() throws Exception {
        String userId = "usr_4455";
        InAppNotificationDto dto = InAppNotificationDto.builder()
                .id(UUID.randomUUID())
                .userId(userId)
                .title("Prescription Ready")
                .content("Your pharmacy prescription is ready for pickup.")
                .category("PHARMACY")
                .isRead(false)
                .createdAt(Instant.now())
                .build();

        when(inAppService.getUserNotifications(eq(userId), any(), any(Pageable.class)))
                .thenReturn(new PageImpl<>(List.of(dto)));

        mockMvc.perform(get("/api/v1/in-app-notifications")
                        .param("userId", userId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].userId").value(userId))
                .andExpect(jsonPath("$.content[0].title").value("Prescription Ready"));
    }

    @Test
    void testGetUnreadCount() throws Exception {
        String userId = "usr_4455";
        when(inAppService.getUnreadCount(userId)).thenReturn(UnreadCountDto.builder()
                .userId(userId)
                .unreadCount(3)
                .build());

        mockMvc.perform(get("/api/v1/in-app-notifications/unread-count")
                        .param("userId", userId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(userId))
                .andExpect(jsonPath("$.unreadCount").value(3));
    }

    @Test
    void testMarkAsRead() throws Exception {
        UUID id = UUID.randomUUID();
        when(inAppService.markAsRead(id)).thenReturn(InAppNotificationDto.builder()
                .id(id)
                .userId("usr_4455")
                .isRead(true)
                .readAt(Instant.now())
                .build());

        mockMvc.perform(patch("/api/v1/in-app-notifications/" + id + "/read"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.read").value(true));
    }

    @Test
    void testMarkAllAsRead() throws Exception {
        String userId = "usr_4455";
        when(inAppService.markAllAsRead(userId)).thenReturn(5);

        mockMvc.perform(patch("/api/v1/in-app-notifications/read-all")
                        .param("userId", userId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.markedAsReadCount").value(5));
    }

    @Test
    void testDeleteNotification() throws Exception {
        UUID id = UUID.randomUUID();

        mockMvc.perform(delete("/api/v1/in-app-notifications/" + id))
                .andExpect(status().isNoContent());
    }
}
