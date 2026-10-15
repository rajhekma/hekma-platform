package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportTicketCreatedResultDto {
    private String ticketId;
    private String ticketNumber;
    private String createdDate;
    private String displayCreatedDate;
    private String status;
    private String displayStatus;
    private Integer slaHours;
    private String expectedResponseText;
}
