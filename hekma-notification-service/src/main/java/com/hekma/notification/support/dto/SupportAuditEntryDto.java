package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportAuditEntryDto {
    private String action;
    private String actorId;
    private String actorName;
    private String details;
    private String createdTs;
}
