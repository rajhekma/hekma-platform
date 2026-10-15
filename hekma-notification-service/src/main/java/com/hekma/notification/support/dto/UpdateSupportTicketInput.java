package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class UpdateSupportTicketInput {
    private String ticketId;
    private String status;
    private String priority;
    private String resolution;
    private String category;
    private String tags;
}
