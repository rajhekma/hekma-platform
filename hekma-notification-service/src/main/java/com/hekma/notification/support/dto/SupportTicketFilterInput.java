package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportTicketFilterInput {
    private String status;
    private String category;
    private String priority;
    private String studyId;
    private String assignedUserId;
    private String createdFrom;
    private String createdTo;
    private Boolean escalated;
    private Boolean slaBreached;
    private String searchText;
}
