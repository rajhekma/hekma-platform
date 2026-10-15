package com.hekma.notification.support.storage;

import com.hekma.notification.support.config.SupportProperties;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.*;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.support.attachment.storage-provider", havingValue = "mock", matchIfMissing = true)
public class MockAttachmentStorageProvider implements AttachmentStorageProvider {

    private static final Set<String> ALLOWED_IMAGE_MIMES = new HashSet<>(Arrays.asList(
            "image/png", "image/jpeg", "image/jpg", "image/heic", "image/heif", "image/webp"
    ));

    private static final Set<String> ALLOWED_EXTENSIONS = new HashSet<>(Arrays.asList(
            "png", "jpeg", "jpg", "heic", "heif", "webp"
    ));

    private final SupportProperties supportProperties;

    public MockAttachmentStorageProvider(SupportProperties supportProperties) {
        this.supportProperties = supportProperties;
        log.info("Initialized MockAttachmentStorageProvider for support attachments");
    }

    @Override
    public PresignedUpload requestPresignedUpload(String filename) {
        if (filename == null || filename.trim().isEmpty()) {
            throw new IllegalArgumentException("filename is required");
        }
        String sanitized = sanitizeFilename(filename.trim());
        validateImageMime("application/octet-stream", sanitized);

        String fileId = UUID.randomUUID().toString();
        String uploadUrl = "https://mock-storage.hekma.local/upload/" + fileId + "/" + sanitized + "?mockPresignedPut=true";
        String fileUrl = "https://mock-storage.hekma.local/files/" + fileId + "/" + sanitized;

        PresignedUpload upload = new PresignedUpload();
        upload.setFileId(fileId);
        upload.setFileName(sanitized);
        upload.setUploadUrl(uploadUrl);
        upload.setFileUrl(fileUrl);
        return upload;
    }

    @Override
    public UploadedImage uploadImage(MultipartFile file, String ticketUuid) throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("File is empty");
        }

        String originalFilename = file.getOriginalFilename();
        String filename = sanitizeFilename(originalFilename != null ? originalFilename : "image");
        String mimeType = resolveMimeType(file.getContentType(), filename);
        validateImageMime(mimeType, filename);

        String fileId = UUID.randomUUID().toString();
        String fileUrl = "https://mock-storage.hekma.local/files/support/" + ticketUuid + "/" + fileId + "/" + filename;

        log.info("Mock stored attachment file {} ({} bytes) for ticket {}", filename, file.getSize(), ticketUuid);

        UploadedImage uploaded = new UploadedImage();
        uploaded.setFileName(filename);
        uploaded.setFileUrl(fileUrl);
        uploaded.setFileSize(file.getSize());
        uploaded.setMimeType(mimeType);
        return uploaded;
    }

    @Override
    public String generatePresignedDownloadUrl(String storedFileUrl) {
        if (storedFileUrl == null || storedFileUrl.trim().isEmpty()) {
            return storedFileUrl;
        }
        return storedFileUrl.contains("?")
                ? storedFileUrl + "&token=mock-presigned-token"
                : storedFileUrl + "?token=mock-presigned-token";
    }

    @Override
    public void validateImageMime(String mimeType, String filename) {
        String normalizedMime = mimeType != null ? mimeType.toLowerCase(Locale.ROOT) : "";
        if (ALLOWED_IMAGE_MIMES.contains(normalizedMime)) {
            return;
        }
        String extension = extensionOf(filename);
        if (extension != null && ALLOWED_EXTENSIONS.contains(extension)) {
            return;
        }
        throw new IllegalArgumentException("Only image files are allowed (PNG, JPEG, HEIC, WEBP)");
    }

    @Override
    public StagedImageRef resolveStagedAttachment(String fileId, String fileName, Integer fileSize, String mimeType) {
        if (fileId == null || fileId.trim().isEmpty()) {
            throw new IllegalArgumentException("fileId is required for each attachment");
        }
        if (fileName == null || fileName.trim().isEmpty()) {
            throw new IllegalArgumentException("fileName is required for each attachment");
        }

        String sanitizedFileName = sanitizeFilename(fileName.trim());
        String resolvedMime = resolveMimeType(mimeType, sanitizedFileName);
        validateImageMime(resolvedMime, sanitizedFileName);

        Long fileSizeBytes = fileSize != null ? fileSize.longValue() : null;
        String fileUrl = "https://mock-storage.hekma.local/files/" + fileId.trim() + "/" + sanitizedFileName;

        StagedImageRef ref = new StagedImageRef();
        ref.setFileName(sanitizedFileName);
        ref.setFileUrl(fileUrl);
        ref.setFileSize(fileSizeBytes);
        ref.setMimeType(resolvedMime);
        return ref;
    }

    private String resolveMimeType(String contentType, String filename) {
        if (contentType != null && !contentType.trim().isEmpty()
                && !"application/octet-stream".equalsIgnoreCase(contentType)) {
            return contentType.toLowerCase(Locale.ROOT);
        }
        String extension = extensionOf(filename);
        if ("png".equals(extension)) return "image/png";
        if ("jpg".equals(extension) || "jpeg".equals(extension)) return "image/jpeg";
        if ("heic".equals(extension)) return "image/heic";
        if ("heif".equals(extension)) return "image/heif";
        if ("webp".equals(extension)) return "image/webp";
        return contentType != null ? contentType : "application/octet-stream";
    }

    private String extensionOf(String filename) {
        if (filename == null || !filename.contains(".")) {
            return null;
        }
        return filename.substring(filename.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
    }

    private String sanitizeFilename(String filename) {
        return filename.replaceAll("[^a-zA-Z0-9._-]", "_");
    }
}
