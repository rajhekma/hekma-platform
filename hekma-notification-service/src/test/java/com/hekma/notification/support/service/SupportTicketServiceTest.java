package com.hekma.notification.support.service;

import com.hekma.notification.support.config.SupportProperties;
import com.hekma.notification.support.domain.entity.*;
import com.hekma.notification.support.domain.repository.*;
import com.hekma.notification.support.dto.*;
import com.hekma.notification.support.storage.AttachmentStorageProvider;
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
class SupportTicketServiceTest {

    @Mock
    private SupportTicketRepository ticketRepository;
    @Mock
    private SupportTicketCommentRepository commentRepository;
    @Mock
    private SupportTicketAttachmentRepository attachmentRepository;
    @Mock
    private SupportTicketAssignmentHistoryRepository assignmentHistoryRepository;
    @Mock
    private SupportTicketStatusHistoryRepository statusHistoryRepository;
    @Mock
    private SupportTicketAuditLogRepository auditLogRepository;
    @Mock
    private SupportSlaTrackingRepository slaRepository;
    @Mock
    private SupportNotificationIntegrationService notificationIntegrationService;
    @Mock
    private SupportOtpService supportOtpService;
    @Mock
    private AttachmentStorageProvider attachmentStorageProvider;

    private SupportProperties supportProperties;
    private SupportTicketService supportTicketService;

    @BeforeEach
    void setUp() {
        supportProperties = new SupportProperties();
        supportTicketService = new SupportTicketService(
                ticketRepository, commentRepository, attachmentRepository,
                assignmentHistoryRepository, statusHistoryRepository, auditLogRepository,
                slaRepository, notificationIntegrationService, supportOtpService,
                attachmentStorageProvider, supportProperties
        );
    }

    @Test
    void listCategories_returnsAllOptions() {
        List<SupportCategoryOptionDto> categories = supportTicketService.listCategories();
        assertNotNull(categories);
        assertFalse(categories.isEmpty());
        assertTrue(categories.stream().anyMatch(c -> "APP_CRASH".equals(c.getCode())));
    }

    @Test
    void createTicket_validatesDescriptionAndPrivacy() {
        CreateSupportTicketInput input = new CreateSupportTicketInput();
        input.setEmail("user@example.com");

        // Missing description
        assertThrows(IllegalArgumentException.class, () ->
                supportTicketService.createTicket(input, null, null, null));

        // Missing privacy accepted
        input.setDescription("Test issue");
        input.setPrivacyAccepted(false);
        assertThrows(IllegalArgumentException.class, () ->
                supportTicketService.createTicket(input, null, null, null));
    }

    @Test
    void createTicket_success() {
        CreateSupportTicketInput input = new CreateSupportTicketInput();
        input.setEmail("patient@example.com");
        input.setDescription("App crashed on login");
        input.setCategory("APP_CRASH");
        input.setPrivacyAccepted(true);

        when(ticketRepository.countTicketsThisYear()).thenReturn(10L);
        when(ticketRepository.save(any(SupportTicketEntity.class))).thenAnswer(inv -> {
            SupportTicketEntity t = inv.getArgument(0);
            t.setId(100L);
            return t;
        });

        SupportTicketCreatedResultDto result = supportTicketService.createTicket(input, null, null, "patient@example.com");

        assertNotNull(result);
        assertNotNull(result.getTicketId());
        assertTrue(result.getTicketNumber().startsWith("SR-"));
        assertEquals("RECEIVED", result.getStatus());
        verify(notificationIntegrationService).notifyTicketEvent(any(SupportTicketEntity.class), eq("TICKET_CREATED"));
    }

    @Test
    void addComment_success() {
        SupportTicketEntity ticket = new SupportTicketEntity();
        ticket.setId(100L);
        ticket.setUuid("uuid-100");
        ticket.setParticipantEmail("user@example.com");

        when(ticketRepository.findByUuid("uuid-100")).thenReturn(Optional.of(ticket));
        when(supportOtpService.validateSessionToken("valid-token")).thenReturn("user@example.com");
        when(commentRepository.save(any(SupportTicketCommentEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        ApiResponse response = supportTicketService.addComment(
                "uuid-100", "I still see this error", null, "User", "PARTICIPANT", false, null, "valid-token");

        assertEquals(200, response.getCode());
        verify(notificationIntegrationService).notifyTicketEvent(ticket, "COMMENT_ADDED");
    }

    @Test
    void getMyTicketSummary_calculatesOpenAndResolved() {
        SupportTicketEntity openTicket = new SupportTicketEntity();
        openTicket.setId(1L);
        openTicket.setStatus("RECEIVED");
        openTicket.setParticipantUserId("usr-1");

        SupportTicketEntity resolvedTicket = new SupportTicketEntity();
        resolvedTicket.setId(2L);
        resolvedTicket.setStatus("RESOLVED");
        resolvedTicket.setParticipantUserId("usr-1");

        when(ticketRepository.findByParticipantUserIdOrderByCreatedTsDesc("usr-1"))
                .thenReturn(Arrays.asList(openTicket, resolvedTicket));

        SupportTicketSummaryStatsDto summary = supportTicketService.getMyTicketSummary("usr-1", null);

        assertEquals(1, summary.getOpenCount());
        assertEquals(1, summary.getResolvedCount());
    }
}
