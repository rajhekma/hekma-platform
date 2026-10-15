package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportTicketDto {
    private String ticketId;
    private String ticketNumber;
    private String subject;
    private String category;
    private String status;
    private String priority;
    private String assignedAgent;
    private String assignedAgentId;
    private String assignedTeam;
    private String participantEmail;
    private String participantUserId;
    private String studyId;
    private String resolution;
    private String tags;
    private Boolean isEscalated;
    private String createdDate;
    private String updatedDate;
    private String slaDueAt;
    private Boolean slaBreached;
    private String description;
    private String diagnosticsJson;
    private Boolean privacyAccepted;
    private String displayStatus;
    private String categoryLabel;
}
