package com.hekma.notification.support.dto;

import lombok.Data;

import java.util.List;

@Data
public class BulkUpdateSupportTicketInput {
    private List<String> ticketIds;
    private String status;
    private String priority;
    private String assignedAgentId;
    private String assignedTeam;
}
