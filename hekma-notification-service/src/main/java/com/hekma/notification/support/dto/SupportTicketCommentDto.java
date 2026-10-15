package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportTicketCommentDto {
    private String commentId;
    private String authorId;
    private String authorName;
    private String authorType;
    private String commentText;
    private Boolean isInternal;
    private String createdTs;
}
