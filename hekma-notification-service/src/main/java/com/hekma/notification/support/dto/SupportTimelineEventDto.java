package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportTimelineEventDto {
    private String eventType;
    private String title;
    private String message;
    private String actorName;
    private String status;
    private String displayStatus;
    private String createdTs;
    private String commentId;
    private String attachmentId;
}
