package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportTicketAttachmentDto {
    private String attachmentId;
    private String fileName;
    private String fileUrl;
    private Integer fileSize;
    private String mimeType;
    private String scanStatus;
    private String uploadedBy;
    private String createdTs;
}
