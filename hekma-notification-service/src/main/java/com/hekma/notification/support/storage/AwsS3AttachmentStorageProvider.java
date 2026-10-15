package com.hekma.notification.support.storage;

import com.hekma.notification.support.config.SupportProperties;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

import java.io.IOException;
import java.time.Duration;
import java.util.*;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.support.attachment.storage-provider", havingValue = "s3")
public class AwsS3AttachmentStorageProvider implements AttachmentStorageProvider {

    private static final Set<String> ALLOWED_IMAGE_MIMES = new HashSet<>(Arrays.asList(
            "image/png", "image/jpeg", "image/jpg", "image/heic", "image/heif", "image/webp"
    ));

    private static final Set<String> ALLOWED_EXTENSIONS = new HashSet<>(Arrays.asList(
            "png", "jpeg", "jpg", "heic", "heif", "webp"
    ));

    private final SupportProperties supportProperties;
    private final S3Client s3Client;
    private final S3Presigner s3Presigner;

    public AwsS3AttachmentStorageProvider(SupportProperties supportProperties) {
        this.supportProperties = supportProperties;
        String regionStr = supportProperties.getAttachment().getS3().getRegion();
        Region region = Region.of(regionStr != null && !regionStr.isBlank() ? regionStr : "us-east-1");

        this.s3Client = S3Client.builder()
                .region(region)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();

        this.s3Presigner = S3Presigner.builder()
                .region(region)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();

        log.info("Initialized AwsS3AttachmentStorageProvider with S3 region {}", region);
    }

    @Override
    public PresignedUpload requestPresignedUpload(String filename) {
        if (filename == null || filename.trim().isEmpty()) {
            throw new IllegalArgumentException("filename is required");
        }
        String sanitized = sanitizeFilename(filename.trim());
        validateImageMime("application/octet-stream", sanitized);

        String fileId = UUID.randomUUID().toString();
        String s3Key = fileId + "/" + sanitized;
        String bucket = supportProperties.getAttachment().getS3().getBucket();

        PutObjectRequest objectRequest = PutObjectRequest.builder()
                .bucket(bucket)
                .key(s3Key)
                .build();

        PutObjectPresignRequest presignRequest = PutObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(15))
                .putObjectRequest(objectRequest)
                .build();

        String putUrl = s3Presigner.presignPutObject(presignRequest).url().toString();

        PresignedUpload upload = new PresignedUpload();
        upload.setFileId(fileId);
        upload.setFileName(sanitized);
        upload.setUploadUrl(putUrl);
        upload.setFileUrl(buildStagedFileUrl(fileId, sanitized));
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
        String s3Key = "support/" + ticketUuid + "/" + fileId + "/" + filename;
        String bucket = supportProperties.getAttachment().getS3().getBucket();

        PutObjectRequest putRequest = PutObjectRequest.builder()
                .bucket(bucket)
                .key(s3Key)
                .contentType(mimeType)
                .contentLength(file.getSize())
                .build();

        s3Client.putObject(putRequest, RequestBody.fromInputStream(file.getInputStream(), file.getSize()));

        String baseUrl = supportProperties.getAttachment().getS3().getBaseUrl();
        String fileUrl = baseUrl.endsWith("/") ? baseUrl + s3Key : baseUrl + "/" + s3Key;

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
        String s3Key = resolveS3KeyFromFileUrl(storedFileUrl.trim());
        if (s3Key == null || s3Key.isEmpty()) {
            return storedFileUrl;
        }

        try {
            String bucket = supportProperties.getAttachment().getS3().getBucket();
            GetObjectRequest getObjectRequest = GetObjectRequest.builder()
                    .bucket(bucket)
                    .key(s3Key)
                    .build();

            GetObjectPresignRequest presignRequest = GetObjectPresignRequest.builder()
                    .signatureDuration(Duration.ofHours(2))
                    .getObjectRequest(getObjectRequest)
                    .build();

            return s3Presigner.presignGetObject(presignRequest).url().toString();
        } catch (Exception e) {
            log.warn("Failed to generate presigned download URL for key {}: {}", s3Key, e.getMessage());
            return storedFileUrl;
        }
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

        StagedImageRef ref = new StagedImageRef();
        ref.setFileName(sanitizedFileName);
        ref.setFileUrl(buildStagedFileUrl(fileId.trim(), sanitizedFileName));
        ref.setFileSize(fileSizeBytes);
        ref.setMimeType(resolvedMime);
        return ref;
    }

    private String buildStagedFileUrl(String fileId, String fileName) {
        String s3Key = fileId.trim() + "/" + sanitizeFilename(fileName.trim());
        String baseUrl = supportProperties.getAttachment().getS3().getBaseUrl();
        return baseUrl.endsWith("/") ? baseUrl + s3Key : baseUrl + "/" + s3Key;
    }

    private String resolveS3KeyFromFileUrl(String fileUrl) {
        String normalized = fileUrl;
        int queryIdx = normalized.indexOf('?');
        if (queryIdx > 0) {
            normalized = normalized.substring(0, queryIdx);
        }

        String baseUrl = supportProperties.getAttachment().getS3().getBaseUrl();
        if (baseUrl != null && !baseUrl.trim().isEmpty()) {
            String base = baseUrl.trim();
            if (base.endsWith("/")) {
                base = base.substring(0, base.length() - 1);
            }
            if (normalized.startsWith(base)) {
                String key = normalized.substring(base.length());
                if (key.startsWith("/")) {
                    key = key.substring(1);
                }
                return key.isEmpty() ? null : key;
            }
        }

        if (normalized.startsWith("https://") || normalized.startsWith("http://")) {
            int schemeEnd = normalized.indexOf("://") + 3;
            int pathStart = normalized.indexOf('/', schemeEnd);
            if (pathStart > 0 && pathStart < normalized.length() - 1) {
                return normalized.substring(pathStart + 1);
            }
        }
        return null;
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
