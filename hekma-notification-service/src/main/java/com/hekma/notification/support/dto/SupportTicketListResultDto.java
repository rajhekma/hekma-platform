package com.hekma.notification.support.dto;

import lombok.Data;

import java.util.List;

@Data
public class SupportTicketListResultDto {
    private List<SupportTicketDto> tickets;
    private Integer totalCount;
    private Integer page;
    private Integer pageSize;
}
