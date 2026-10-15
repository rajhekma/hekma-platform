package com.hekma.notification.support.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class SupportTicketSummaryStatsDto {
    private Integer openCount;
    private Integer resolvedCount;
}
