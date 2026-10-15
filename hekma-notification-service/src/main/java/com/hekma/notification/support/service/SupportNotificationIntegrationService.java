package com.hekma.notification.support.service;

import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationPriority;
import com.hekma.notification.dto.NotificationSendRequest;
import com.hekma.notification.service.NotificationDispatcherService;
import com.hekma.notification.support.domain.entity.SupportTicketEntity;
import com.hekma.notification.support.domain.entity.SupportTicketNotificationHistoryEntity;
import com.hekma.notification.support.domain.repository.SupportTicketNotificationHistoryRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
public class SupportNotificationIntegrationService {

    private final NotificationDispatcherService notificationDispatcherService;
    private final SupportTicketNotificationHistoryRepository notificationHistoryRepository;

    public SupportNotificationIntegrationService(
            NotificationDispatcherService notificationDispatcherService,
            SupportTicketNotificationHistoryRepository notificationHistoryRepository) {
        this.notificationDispatcherService = notificationDispatcherService;
        this.notificationHistoryRepository = notificationHistoryRepository;
    }

    public void notifyTicketEvent(SupportTicketEntity ticket, String eventType) {
        try {
            sendEmailNotification(ticket, eventType);
            sendInAppNotification(ticket, eventType);
        } catch (Exception e) {
            log.error("Failed to process notifications for ticket {} event {}", ticket.getTicketNumber(), eventType, e);
        }
    }

    private void sendEmailNotification(SupportTicketEntity ticket, String eventType) {
        if (ticket.getParticipantEmail() == null || ticket.getParticipantEmail().trim().isEmpty()) {
            return;
        }

        String subject = buildEmailSubject(ticket, eventType);
        String body = buildEmailBody(ticket, eventType);

        try {
            NotificationSendRequest request = new NotificationSendRequest();
            request.setChannel(NotificationChannel.EMAIL);
            request.setRecipient(ticket.getParticipantEmail().trim());
            request.setTitle(subject);
            request.setContent(body);
            request.setPriority(NotificationPriority.NORMAL);
            request.setSourceService("hekma-notification-service");
            request.setAsync(true);

            notificationDispatcherService.sendNotification(request);
            recordNotification(ticket.getId(), eventType, "EMAIL", ticket.getParticipantEmail(),
                    ticket.getParticipantUserId(), "SENT", null);
        } catch (Exception e) {
            log.warn("Email notification failed for ticket {}", ticket.getTicketNumber(), e);
            recordNotification(ticket.getId(), eventType, "EMAIL", ticket.getParticipantEmail(),
                    ticket.getParticipantUserId(), "FAILED", e.getMessage());
        }
    }

    private void sendInAppNotification(SupportTicketEntity ticket, String eventType) {
        if (ticket.getParticipantUserId() == null || ticket.getParticipantUserId().trim().isEmpty()) {
            return;
        }

        String title = buildInAppTitle(ticket, eventType);
        String body = buildInAppBody(ticket, eventType);

        try {
            NotificationSendRequest request = new NotificationSendRequest();
            request.setChannel(NotificationChannel.IN_APP);
            request.setRecipient(ticket.getParticipantUserId().trim());
            request.setTitle(title);
            request.setContent(body);
            request.setPriority(NotificationPriority.NORMAL);
            request.setSourceService("hekma-notification-service");
            Map<String, Object> metadata = new HashMap<>();
            metadata.put("ticketId", ticket.getUuid());
            metadata.put("ticketNumber", ticket.getTicketNumber());
            request.setMetadata(metadata);
            request.setAsync(true);

            notificationDispatcherService.sendNotification(request);
            recordNotification(ticket.getId(), eventType, "IN_APP", null,
                    ticket.getParticipantUserId(), "SENT", null);
        } catch (Exception e) {
            log.warn("In-app notification failed for ticket {}", ticket.getTicketNumber(), e);
            recordNotification(ticket.getId(), eventType, "IN_APP", null,
                    ticket.getParticipantUserId(), "FAILED", e.getMessage());
        }
    }

    private String buildEmailSubject(SupportTicketEntity ticket, String eventType) {
        switch (eventType) {
            case "TICKET_CREATED":
                return "HEKMA Support: Request Received [" + ticket.getTicketNumber() + "]";
            case "ASSIGNED":
                return "HEKMA Support: Ticket Assigned [" + ticket.getTicketNumber() + "]";
            case "AGENT_REPLY":
                return "HEKMA Support: Update on Ticket [" + ticket.getTicketNumber() + "]";
            case "TICKET_ESCALATED":
                return "HEKMA Support: Ticket Escalated [" + ticket.getTicketNumber() + "]";
            case "STATUS_CHANGED":
                return "HEKMA Support: Status Changed [" + ticket.getTicketNumber() + "]";
            default:
                return "HEKMA Support Update [" + ticket.getTicketNumber() + "]";
        }
    }

    private String buildEmailBody(SupportTicketEntity ticket, String eventType) {
        return "Hello,\n\nYour support ticket " + ticket.getTicketNumber() + " (" + ticket.getSubject() +
                ") has an update. Current status: " + SupportCategoryCatalog.toDisplayStatus(ticket.getStatus()) +
                ".\n\nThank you,\nHEKMA Support Team";
    }

    private String buildInAppTitle(SupportTicketEntity ticket, String eventType) {
        return "Support Ticket Update (" + ticket.getTicketNumber() + ")";
    }

    private String buildInAppBody(SupportTicketEntity ticket, String eventType) {
        return "Ticket " + ticket.getTicketNumber() + " status is now " +
                SupportCategoryCatalog.toDisplayStatus(ticket.getStatus()) + ".";
    }

    private void recordNotification(Long ticketId, String eventType, String channel,
                                    String email, String userId, String status, String error) {
        try {
            SupportTicketNotificationHistoryEntity record = new SupportTicketNotificationHistoryEntity();
            record.setTicketId(ticketId);
            record.setNotificationType(eventType);
            record.setChannel(channel);
            record.setRecipientEmail(email);
            record.setRecipientUserId(userId);
            record.setStatus(status);
            record.setErrorMessage(error);
            notificationHistoryRepository.save(record);
        } catch (Exception e) {
            log.warn("Could not record notification history for ticket {}: {}", ticketId, e.getMessage());
        }
    }
}
