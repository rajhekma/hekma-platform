package com.hekma.notification.support.dto;

import lombok.Data;

import java.util.List;

@Data
public class SupportTicketDetailDto {
    private SupportTicketDto ticket;
    private List<SupportTicketCommentDto> conversationHistory;
    private List<SupportTicketAttachmentDto> attachments;
    private String internalStatus;
    private SupportSlaInfoDto sla;
    private String assignedAgent;
    private String resolution;
    private List<SupportAuditEntryDto> auditTimeline;
    private List<SupportTimelineEventDto> timeline;
}
