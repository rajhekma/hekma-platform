package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class PresignedUploadResponseDto {
    private String fileId;
    private String fileName;
    private String uploadUrl;
    private String fileUrl;
}
