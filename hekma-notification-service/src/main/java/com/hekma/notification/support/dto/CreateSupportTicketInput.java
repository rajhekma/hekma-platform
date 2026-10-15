package com.hekma.notification.support.dto;

import lombok.Data;

import java.util.List;

@Data
public class CreateSupportTicketInput {
    private String subject;
    private String description;
    private String category;
    private String priority;
    private String studyId;
    private String diagnosticsJson;
    private Boolean privacyAccepted;
    private String email;
    private List<SupportAttachmentRefInput> attachments;
}
