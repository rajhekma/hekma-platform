package com.hekma.notification.support.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.notification.config.GlobalExceptionHandler;
import com.hekma.notification.support.dto.*;
import com.hekma.notification.support.service.SupportOtpService;
import com.hekma.notification.support.service.SupportTicketService;
import com.hekma.notification.support.storage.AttachmentStorageProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Collections;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class SupportPublicControllerTest {

    private MockMvc mockMvc;

    @Mock
    private SupportOtpService supportOtpService;

    @Mock
    private SupportTicketService supportTicketService;

    @Mock
    private AttachmentStorageProvider attachmentStorageProvider;

    @InjectMocks
    private SupportPublicController supportPublicController;

    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(supportPublicController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
        objectMapper = new ObjectMapper();
    }

    @Test
    void sendOtp_success() throws Exception {
        SupportOtpResultDto result = new SupportOtpResultDto();
        result.setSuccess(true);
        result.setChallengeId("test-challenge-1");
        result.setMessage("Verification code sent.");

        when(supportOtpService.sendOtp("test@example.com")).thenReturn(result);

        SupportPublicController.SendOtpRequest request = new SupportPublicController.SendOtpRequest();
        request.setEmail("test@example.com");

        mockMvc.perform(post("/api/v1/support/public/otp/send")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.challengeId").value("test-challenge-1"));
    }

    @Test
    void verifyOtp_success() throws Exception {
        SupportOtpVerifyResultDto result = new SupportOtpVerifyResultDto();
        result.setSuccess(true);
        result.setOtpToken("session-token-abc");
        result.setMessage("Email verified successfully.");

        when(supportOtpService.verifyOtp("test-challenge-1", "123456")).thenReturn(result);

        SupportPublicController.VerifyOtpRequest request = new SupportPublicController.VerifyOtpRequest();
        request.setChallengeId("test-challenge-1");
        request.setOtpCode("123456");

        mockMvc.perform(post("/api/v1/support/public/otp/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.otpToken").value("session-token-abc"));
    }

    @Test
    void fileUpload_requiresOtpToken() throws Exception {
        SupportPublicController.FileUploadRequest request = new SupportPublicController.FileUploadRequest();
        request.setFilename("screen.png");

        mockMvc.perform(post("/api/v1/support/public/file-upload")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(401))
                .andExpect(jsonPath("$.message").value("X-Support-Otp-Token header is required"));
    }

    @Test
    void createTicket_success() throws Exception {
        when(supportOtpService.validateSessionToken("valid-token")).thenReturn("user@example.com");

        SupportTicketCreatedResultDto created = new SupportTicketCreatedResultDto();
        created.setTicketId("ticket-uuid-1");
        created.setTicketNumber("SR-2026-000001");
        created.setStatus("RECEIVED");

        when(supportTicketService.createTicket(any(), any(), any(), eq("user@example.com")))
                .thenReturn(created);

        SupportPublicController.CreatePublicTicketRequest request = new SupportPublicController.CreatePublicTicketRequest();
        request.setEmail("user@example.com");
        request.setDescription("Help with login");
        request.setPrivacyAccepted(true);

        mockMvc.perform(post("/api/v1/support/public/tickets")
                        .header("X-Support-Otp-Token", "valid-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.ticketNumber").value("SR-2026-000001"));
    }

    @Test
    void listTickets_success() throws Exception {
        SupportTicketListResultDto listResult = new SupportTicketListResultDto();
        listResult.setTickets(Collections.emptyList());
        listResult.setTotalCount(0);

        when(supportTicketService.getPublicTickets(eq("user@example.com"), eq("valid-token"), any(), any(), any()))
                .thenReturn(listResult);

        mockMvc.perform(get("/api/v1/support/public/tickets")
                        .header("X-Support-Otp-Token", "valid-token")
                        .param("email", "user@example.com"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.totalCount").value(0));
    }
}
