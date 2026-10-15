package com.hekma.notification.support.controller;

import com.hekma.notification.support.domain.entity.SupportTicketAttachmentEntity;
import com.hekma.notification.support.dto.*;
import com.hekma.notification.support.service.SupportCategoryCatalog;
import com.hekma.notification.support.service.SupportOtpService;
import com.hekma.notification.support.service.SupportTicketService;
import com.hekma.notification.support.storage.AttachmentStorageProvider;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import io.swagger.v3.oas.annotations.tags.Tag;

import java.util.List;

@Slf4j
@RestController
@RequestMapping("/api/v1/support/public")
@Tag(name = "Support Center - Public", description = "Guest support endpoints for ticket creation, OTP verification, comment updates, and file uploads")
public class SupportPublicController {

    private static final String OTP_TOKEN_HEADER = "X-Support-Otp-Token";

    private final SupportOtpService supportOtpService;
    private final SupportTicketService supportTicketService;
    private final AttachmentStorageProvider attachmentStorageProvider;

    public SupportPublicController(SupportOtpService supportOtpService,
                                   SupportTicketService supportTicketService,
                                   AttachmentStorageProvider attachmentStorageProvider) {
        this.supportOtpService = supportOtpService;
        this.supportTicketService = supportTicketService;
        this.attachmentStorageProvider = attachmentStorageProvider;
    }

    @PostMapping("/file-upload")
    public RestResponse<PresignedUploadResponseDto> requestPresignedUpload(
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken,
            @RequestBody FileUploadRequest request) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        if (supportOtpService.validateSessionToken(otpToken.trim()) == null) {
            return RestResponse.error(401, "Invalid or expired verification token");
        }
        if (request == null || request.getFilename() == null || request.getFilename().trim().isEmpty()) {
            return RestResponse.error(400, "filename is required");
        }
        try {
            AttachmentStorageProvider.PresignedUpload upload =
                    attachmentStorageProvider.requestPresignedUpload(request.getFilename().trim());
            PresignedUploadResponseDto data = new PresignedUploadResponseDto();
            data.setFileId(upload.getFileId());
            data.setFileName(upload.getFileName());
            data.setUploadUrl(upload.getUploadUrl());
            data.setFileUrl(upload.getFileUrl());
            return RestResponse.success("Presigned upload URL generated.", data);
        } catch (IllegalArgumentException e) {
            return RestResponse.error(400, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to generate support public presigned upload URL", e);
            return RestResponse.error(500, "Failed to prepare file upload.");
        }
    }

    @PostMapping("/otp/send")
    public RestResponse<SupportOtpResultDto> sendOtp(@RequestBody SendOtpRequest request) {
        if (request == null || request.getEmail() == null || request.getEmail().trim().isEmpty()) {
            return RestResponse.error(400, "email is required");
        }
        try {
            SupportOtpResultDto result = supportOtpService.sendOtp(request.getEmail().trim());
            if (Boolean.TRUE.equals(result.getSuccess())) {
                return RestResponse.success(result.getMessage(), result);
            }
            int code = result.getRetryAfter() != null ? 429 : 400;
            return new RestResponse<>(code, "error", result.getMessage(), result);
        } catch (Exception e) {
            log.error("Failed to send support OTP", e);
            return RestResponse.error(500, "We could not send the verification code. Please try again.");
        }
    }

    @PostMapping("/otp/verify")
    public RestResponse<SupportOtpVerifyResultDto> verifyOtp(@RequestBody VerifyOtpRequest request) {
        if (request == null || request.getChallengeId() == null || request.getOtpCode() == null) {
            return RestResponse.error(400, "challengeId and otpCode are required");
        }
        SupportOtpVerifyResultDto result = supportOtpService.verifyOtp(
                request.getChallengeId().trim(), request.getOtpCode().trim());
        if (Boolean.TRUE.equals(result.getSuccess())) {
            return RestResponse.success(result.getMessage(), result);
        }
        return new RestResponse<>(401, "error", result.getMessage(), result);
    }

    @PostMapping("/tickets")
    public RestResponse<SupportTicketCreatedResultDto> createTicket(
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken,
            @RequestBody CreatePublicTicketRequest request) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        String verifiedEmail = supportOtpService.validateSessionToken(otpToken.trim());
        if (verifiedEmail == null) {
            return RestResponse.error(401, "Invalid or expired verification token");
        }
        if (request == null || request.getEmail() == null || request.getEmail().trim().isEmpty()) {
            return RestResponse.error(400, "email is required");
        }
        if (!verifiedEmail.equalsIgnoreCase(request.getEmail().trim())) {
            return RestResponse.error(403, "Email does not match verified session");
        }
        if (request.getDescription() == null || request.getDescription().trim().isEmpty()) {
            return RestResponse.error(400, "description is required");
        }
        if (!Boolean.TRUE.equals(request.getPrivacyAccepted())) {
            return RestResponse.error(400, "privacyAccepted must be true");
        }

        CreateSupportTicketInput input = new CreateSupportTicketInput();
        input.setEmail(request.getEmail().trim());
        input.setSubject(request.getSubject());
        input.setDescription(request.getDescription().trim());
        input.setCategory(request.getCategory() != null ? request.getCategory() : SupportCategoryCatalog.OTHER_INQUIRIES);
        input.setPriority(request.getPriority() != null ? request.getPriority() : "MEDIUM");
        input.setStudyId(request.getStudyId());
        input.setDiagnosticsJson(request.getDiagnosticsJson());
        input.setPrivacyAccepted(true);
        input.setAttachments(request.getAttachments());

        try {
            SupportTicketCreatedResultDto created = supportTicketService.createTicket(
                    input, null, null, request.getEmail().trim());
            return RestResponse.success("Support ticket created", created);
        } catch (IllegalArgumentException e) {
            return RestResponse.error(400, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to create public support ticket", e);
            return RestResponse.error(500, "Failed to create support ticket");
        }
    }

    @GetMapping("/tickets")
    public RestResponse<SupportTicketListResultDto> listTickets(
            @RequestParam String email,
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String searchText,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        if (email == null || email.trim().isEmpty()) {
            return RestResponse.error(400, "email is required");
        }
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        try {
            SupportTicketFilterInput filter = new SupportTicketFilterInput();
            filter.setStatus(status);
            filter.setSearchText(searchText);
            SupportPaginationInput pagination = new SupportPaginationInput();
            pagination.setPage(page);
            pagination.setPageSize(pageSize);
            SupportSortInput sort = new SupportSortInput();
            sort.setField("createdTs");
            sort.setDirection("DESC");

            SupportTicketListResultDto result = supportTicketService.getPublicTickets(
                    email.trim(), otpToken.trim(), filter, pagination, sort);
            return RestResponse.success("Tickets retrieved successfully.", result);
        } catch (SecurityException e) {
            return RestResponse.error(403, e.getMessage());
        }
    }

    @GetMapping("/tickets/{ticketId}")
    public RestResponse<SupportTicketDetailDto> getTicket(
            @PathVariable String ticketId,
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        try {
            String email = supportOtpService.validateSessionToken(otpToken.trim());
            if (email == null) {
                return RestResponse.error(401, "Invalid or expired verification token");
            }
            SupportTicketDetailDto detail = supportTicketService.getTicketDetail(
                    ticketId, null, email, otpToken.trim());
            return RestResponse.success("Ticket retrieved successfully.", detail);
        } catch (SecurityException e) {
            return RestResponse.error(403, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to get public ticket {}", ticketId, e);
            return RestResponse.error(404, "Ticket not found");
        }
    }

    @PostMapping("/tickets/{ticketId}/comments")
    public RestResponse<CommentCreatedResponse> addComment(
            @PathVariable String ticketId,
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken,
            @RequestBody AddCommentRequest request) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        if (request == null || request.getCommentText() == null || request.getCommentText().trim().isEmpty()) {
            return RestResponse.error(400, "commentText is required");
        }
        try {
            ApiResponse response = supportTicketService.addComment(
                    ticketId, request.getCommentText().trim(), null, null, "PARTICIPANT", false, null, otpToken.trim());
            if (response.getCode() == 200) {
                CommentCreatedResponse data = new CommentCreatedResponse();
                data.setCommentId(response.getAttributes());
                return RestResponse.success(response.getMessage(), data);
            }
            return RestResponse.error(response.getCode(), response.getMessage());
        } catch (SecurityException e) {
            return RestResponse.error(403, e.getMessage());
        }
    }

    @PostMapping("/tickets/{ticketId}/escalate")
    public RestResponse<Object> escalateTicket(
            @PathVariable String ticketId,
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken,
            @RequestBody(required = false) EscalateRequest request) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        String reason = request != null ? request.getReason() : null;
        try {
            ApiResponse response = supportTicketService.escalateTicket(
                    ticketId, "public", reason, null, otpToken.trim());
            if (response.getCode() == 200) {
                return RestResponse.success(response.getMessage(), null);
            }
            return RestResponse.error(response.getCode(), response.getMessage());
        } catch (SecurityException e) {
            return RestResponse.error(403, e.getMessage());
        }
    }

    @PostMapping(value = "/tickets/{ticketId}/attachments", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public RestResponse<List<SupportTicketAttachmentDto>> uploadAttachments(
            @PathVariable String ticketId,
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken,
            @RequestPart("files") MultipartFile[] files) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        try {
            List<SupportTicketAttachmentDto> uploaded = supportTicketService.uploadImageAttachments(
                    ticketId, files, null, null, otpToken.trim());
            return RestResponse.success("Images uploaded successfully.", uploaded);
        } catch (SecurityException e) {
            return RestResponse.error(403, e.getMessage());
        } catch (IllegalArgumentException e) {
            return RestResponse.error(400, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to upload public support attachments for ticket {}", ticketId, e);
            return RestResponse.error(500, "Failed to upload images. Please try again.");
        }
    }

    @PostMapping(value = "/tickets/{ticketId}/attachments/metadata", consumes = MediaType.APPLICATION_JSON_VALUE)
    public RestResponse<AttachmentCreatedResponse> uploadAttachmentMetadata(
            @PathVariable String ticketId,
            @RequestHeader(value = OTP_TOKEN_HEADER, required = false) String otpToken,
            @RequestBody UploadAttachmentRequest request) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return RestResponse.error(401, "X-Support-Otp-Token header is required");
        }
        if (request == null || request.getFileName() == null || request.getFileUrl() == null) {
            return RestResponse.error(400, "fileName and fileUrl are required");
        }
        try {
            ApiResponse response = supportTicketService.uploadAttachment(
                    ticketId, request.getFileName(), request.getFileUrl(),
                    request.getFileSize(), request.getMimeType(), "public", null, otpToken.trim());
            if (response.getCode() == 200) {
                AttachmentCreatedResponse data = new AttachmentCreatedResponse();
                data.setAttachmentId(response.getAttributes());
                return RestResponse.success(response.getMessage(), data);
            }
            return RestResponse.error(response.getCode(), response.getMessage());
        } catch (SecurityException e) {
            return RestResponse.error(403, e.getMessage());
        }
    }

    @Data
    public static class SendOtpRequest {
        private String email;
    }

    @Data
    public static class VerifyOtpRequest {
        private String challengeId;
        private String otpCode;
    }

    @Data
    public static class CreatePublicTicketRequest {
        private String email;
        private String subject;
        private String description;
        private String category;
        private String priority;
        private String studyId;
        private String diagnosticsJson;
        private Boolean privacyAccepted;
        private List<SupportAttachmentRefInput> attachments;
    }

    @Data
    public static class FileUploadRequest {
        private String filename;
    }

    @Data
    public static class AddCommentRequest {
        private String commentText;
    }

    @Data
    public static class EscalateRequest {
        private String reason;
    }

    @Data
    public static class UploadAttachmentRequest {
        private String fileName;
        private String fileUrl;
        private Integer fileSize;
        private String mimeType;
    }

    @Data
    public static class CommentCreatedResponse {
        private String commentId;
    }

    @Data
    public static class AttachmentCreatedResponse {
        private String attachmentId;
    }
}
