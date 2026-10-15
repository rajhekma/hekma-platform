package com.hekma.notification.support.storage;

import lombok.Data;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

public interface AttachmentStorageProvider {

    PresignedUpload requestPresignedUpload(String filename) throws Exception;

    UploadedImage uploadImage(MultipartFile file, String ticketUuid) throws IOException;

    String generatePresignedDownloadUrl(String storedFileUrl);

    void validateImageMime(String mimeType, String filename);

    StagedImageRef resolveStagedAttachment(String fileId, String fileName, Integer fileSize, String mimeType);

    @Data
    class PresignedUpload {
        private String fileId;
        private String fileName;
        private String uploadUrl;
        private String fileUrl;
    }

    @Data
    class UploadedImage {
        private String fileName;
        private String fileUrl;
        private Long fileSize;
        private String mimeType;
    }

    @Data
    class StagedImageRef {
        private String fileName;
        private String fileUrl;
        private Long fileSize;
        private String mimeType;
    }
}
