package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportAttachmentRefInput {
    private String fileId;
    private String fileName;
    private Integer fileSize;
    private String mimeType;
}
