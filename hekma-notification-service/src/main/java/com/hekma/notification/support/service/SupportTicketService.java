package com.hekma.notification.support.service;

import com.hekma.notification.support.config.SupportProperties;
import com.hekma.notification.support.domain.entity.*;
import com.hekma.notification.support.domain.repository.*;
import com.hekma.notification.support.dto.*;
import com.hekma.notification.support.storage.AttachmentStorageProvider;
import jakarta.persistence.criteria.Predicate;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
public class SupportTicketService {

    private static final String DATETIME_FORMAT = "yyyy-MM-dd HH:mm:ss";
    private static final String DISPLAY_DATETIME_FORMAT = "dd MMM yyyy, hh:mm a";
    private static final List<String> VALID_STATUSES = Arrays.asList(
            "DRAFT", "RECEIVED", "SUBMITTED", "ASSIGNED", "IN_REVIEW",
            "AWAITING_USER_RESPONSE", "RESOLVED", "CLOSED", "ESCALATED"
    );
    private static final Set<String> RESOLVED_STATUSES = new HashSet<>(Arrays.asList("RESOLVED", "CLOSED"));

    private final SupportTicketRepository ticketRepository;
    private final SupportTicketCommentRepository commentRepository;
    private final SupportTicketAttachmentRepository attachmentRepository;
    private final SupportTicketAssignmentHistoryRepository assignmentHistoryRepository;
    private final SupportTicketStatusHistoryRepository statusHistoryRepository;
    private final SupportTicketAuditLogRepository auditLogRepository;
    private final SupportSlaTrackingRepository slaRepository;
    private final SupportNotificationIntegrationService notificationIntegrationService;
    private final SupportOtpService supportOtpService;
    private final AttachmentStorageProvider attachmentStorageProvider;
    private final SupportProperties supportProperties;

    public SupportTicketService(SupportTicketRepository ticketRepository,
                                SupportTicketCommentRepository commentRepository,
                                SupportTicketAttachmentRepository attachmentRepository,
                                SupportTicketAssignmentHistoryRepository assignmentHistoryRepository,
                                SupportTicketStatusHistoryRepository statusHistoryRepository,
                                SupportTicketAuditLogRepository auditLogRepository,
                                SupportSlaTrackingRepository slaRepository,
                                SupportNotificationIntegrationService notificationIntegrationService,
                                SupportOtpService supportOtpService,
                                AttachmentStorageProvider attachmentStorageProvider,
                                SupportProperties supportProperties) {
        this.ticketRepository = ticketRepository;
        this.commentRepository = commentRepository;
        this.attachmentRepository = attachmentRepository;
        this.assignmentHistoryRepository = assignmentHistoryRepository;
        this.statusHistoryRepository = statusHistoryRepository;
        this.auditLogRepository = auditLogRepository;
        this.slaRepository = slaRepository;
        this.notificationIntegrationService = notificationIntegrationService;
        this.supportOtpService = supportOtpService;
        this.attachmentStorageProvider = attachmentStorageProvider;
        this.supportProperties = supportProperties;
    }

    public List<SupportCategoryOptionDto> listCategories() {
        return SupportCategoryCatalog.listCategories();
    }

    public SupportTicketSummaryStatsDto getMyTicketSummary(String userId, String userEmail) {
        SupportTicketSummaryStatsDto stats = new SupportTicketSummaryStatsDto();
        List<SupportTicketEntity> entities = findAccessibleParticipantTickets(userId, userEmail);
        long resolvedCount = entities.stream()
                .filter(t -> RESOLVED_STATUSES.contains(SupportCategoryCatalog.normalizeStatus(t.getStatus())))
                .count();
        stats.setResolvedCount((int) resolvedCount);
        stats.setOpenCount(entities.size() - (int) resolvedCount);
        return stats;
    }

    public String resolveAuthenticatedUserEmail(String userId, String jwtEmail) {
        return resolveParticipantEmail(userId, jwtEmail, null);
    }

    @Transactional
    public SupportTicketCreatedResultDto createTicket(CreateSupportTicketInput input, String userId, String userType, String userEmail) {
        if (input.getDescription() == null || input.getDescription().trim().isEmpty()) {
            throw new IllegalArgumentException("Description is required");
        }
        if (!Boolean.TRUE.equals(input.getPrivacyAccepted())) {
            throw new IllegalArgumentException("Privacy notice must be accepted");
        }

        String email = resolveParticipantEmail(userId, userEmail, input.getEmail());
        if (email == null || email.trim().isEmpty()) {
            throw new IllegalArgumentException("Email is required");
        }

        String category = SupportCategoryCatalog.normalizeCode(
                input.getCategory() != null ? input.getCategory() : SupportCategoryCatalog.OTHER_INQUIRIES);
        if (!SupportCategoryCatalog.isValid(category)) {
            throw new IllegalArgumentException("Invalid support category");
        }

        String subject = input.getSubject() != null && !input.getSubject().trim().isEmpty()
                ? input.getSubject().trim()
                : SupportCategoryCatalog.defaultSubjectFor(category);

        SupportTicketEntity ticket = new SupportTicketEntity();
        ticket.setTicketNumber(generateTicketNumber());
        ticket.setSubject(subject);
        ticket.setDescription(input.getDescription().trim());
        ticket.setCategory(category);
        ticket.setPriority(input.getPriority() != null ? input.getPriority().toUpperCase() : "MEDIUM");
        ticket.setStatus("RECEIVED");
        ticket.setParticipantEmail(email.trim().toLowerCase());
        ticket.setParticipantUserId(userId);
        ticket.setParticipantUserType(userType);
        ticket.setStudyId(input.getStudyId());
        ticket.setDiagnosticsJson(input.getDiagnosticsJson());
        ticket.setPrivacyAccepted(true);
        ticket.setCreatedBy(userId != null ? userId : email);

        ticket = ticketRepository.save(ticket);

        createSlaTracking(ticket);
        recordStatusChange(ticket.getId(), null, "RECEIVED", userId, userId, "Ticket created");
        auditLog(ticket.getId(), "TICKET_CREATED", userId, userId, "Ticket " + ticket.getTicketNumber() + " created");

        String uploadedBy = userId != null ? userId : email;
        linkStagedAttachments(ticket, input.getAttachments(), uploadedBy);

        notificationIntegrationService.notifyTicketEvent(ticket, "TICKET_CREATED");

        return mapCreatedResult(ticket);
    }

    public SupportTicketListResultDto getMyTickets(String userId, String userEmail,
                                                   SupportTicketFilterInput filter,
                                                   SupportPaginationInput pagination,
                                                   SupportSortInput sort) {
        List<SupportTicketEntity> entities = findAccessibleParticipantTickets(userId, userEmail);
        entities = applyInMemoryFilters(entities, filter);
        return paginateAndMap(entities, pagination, sort);
    }

    public SupportTicketListResultDto getPublicTickets(String email, String otpToken,
                                                       SupportTicketFilterInput filter,
                                                       SupportPaginationInput pagination,
                                                       SupportSortInput sort) {
        String verifiedEmail = supportOtpService.validateSessionToken(otpToken);
        if (verifiedEmail == null || !verifiedEmail.equalsIgnoreCase(email.trim())) {
            throw new SecurityException("Invalid or expired verification token");
        }

        List<SupportTicketEntity> entities = ticketRepository
                .findByParticipantEmailIgnoreCaseOrderByCreatedTsDesc(email.trim().toLowerCase());
        entities = applyInMemoryFilters(entities, filter);
        return paginateAndMap(entities, pagination, sort);
    }

    public SupportTicketDetailDto getTicketDetail(String ticketId, String userId, String userEmail, String otpToken) {
        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);
        authorizeTicketAccess(entity, userId, userEmail, otpToken);
        return buildTicketDetail(entity, false);
    }

    public SupportTicketDetailDto getAdminTicketDetail(String ticketId) {
        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);
        return buildTicketDetail(entity, true);
    }

    public SupportTicketListResultDto getAdminTickets(SupportTicketFilterInput filter,
                                                      SupportPaginationInput pagination,
                                                      SupportSortInput sort) {
        Specification<SupportTicketEntity> spec = buildSpecification(filter);
        int page = pagination != null && pagination.getPage() != null ? pagination.getPage() : 0;
        int size = pagination != null && pagination.getPageSize() != null ? pagination.getPageSize() : 20;
        String sortField = sort != null && sort.getField() != null ? sort.getField() : "createdTs";
        Sort.Direction direction = sort != null && "ASC".equalsIgnoreCase(sort.getDirection())
                ? Sort.Direction.ASC : Sort.Direction.DESC;

        Page<SupportTicketEntity> pageResult = ticketRepository.findAll(
                spec, PageRequest.of(page, size, Sort.by(direction, mapSortField(sortField))));

        SupportTicketListResultDto result = new SupportTicketListResultDto();
        result.setTickets(pageResult.getContent().stream().map(this::mapToTicket).collect(Collectors.toList()));
        result.setTotalCount((int) pageResult.getTotalElements());
        result.setPage(page);
        result.setPageSize(size);
        return result;
    }

    @Transactional
    public ApiResponse addComment(String ticketId, String commentText, String authorId,
                                  String authorName, String authorType, boolean isInternal,
                                  String userEmail, String otpToken) {
        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);
        if (!isInternal && "PARTICIPANT".equalsIgnoreCase(authorType)) {
            authorizeTicketAccess(entity, authorId, userEmail, otpToken);
        }

        SupportTicketCommentEntity comment = new SupportTicketCommentEntity();
        comment.setTicketId(entity.getId());
        comment.setAuthorId(authorId);
        comment.setAuthorName(authorName);
        comment.setAuthorType(authorType != null ? authorType : "PARTICIPANT");
        comment.setCommentText(commentText);
        comment.setIsInternal(isInternal);
        commentRepository.save(comment);

        auditLog(entity.getId(), "COMMENT_ADDED", authorId, authorName,
                isInternal ? "Internal note added" : "Comment added");

        if (!isInternal) {
            notificationIntegrationService.notifyTicketEvent(entity, "COMMENT_ADDED");
        }

        return new ApiResponse(200, "success", "Comment added", comment.getUuid());
    }

    @Transactional
    public ApiResponse uploadAttachment(String ticketId, String fileName, String fileUrl,
                                        Integer fileSize, String mimeType, String uploadedBy,
                                        String userEmail, String otpToken) {
        return uploadAttachment(ticketId, fileName, fileUrl, fileSize, mimeType,
                uploadedBy, userEmail, otpToken, false);
    }

    @Transactional
    public ApiResponse uploadAttachment(String ticketId, String fileName, String fileUrl,
                                        Integer fileSize, String mimeType, String uploadedBy,
                                        String userEmail, String otpToken, boolean adminAccess) {
        Long fileSizeBytes = fileSize != null ? fileSize.longValue() : null;
        long maxAttachmentSize = supportProperties.getAttachment().getMaxSizeBytes();
        if (fileSizeBytes != null && fileSizeBytes > maxAttachmentSize) {
            return new ApiResponse(400, "error",
                    "Attachment exceeds maximum size of " + (maxAttachmentSize / 1048576) + "MB", "");
        }

        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);
        if (!adminAccess) {
            authorizeTicketAccess(entity, uploadedBy, userEmail, otpToken);
        }
        ensureAttachmentCapacity(entity.getId(), 1);

        try {
            attachmentStorageProvider.validateImageMime(
                    mimeType != null ? mimeType : "application/octet-stream", fileName);
        } catch (IllegalArgumentException ex) {
            return new ApiResponse(400, "error", ex.getMessage(), "");
        }

        SupportTicketAttachmentEntity attachment = persistAttachment(
                entity, fileName, fileUrl, fileSizeBytes, mimeType, uploadedBy);
        return new ApiResponse(200, "success", "Attachment uploaded", attachment.getUuid());
    }

    @Transactional
    public List<SupportTicketAttachmentDto> uploadImageAttachments(String ticketId, MultipartFile[] files,
                                                                   String uploadedBy, String userEmail,
                                                                   String otpToken) throws IOException {
        if (files == null || files.length == 0) {
            throw new IllegalArgumentException("No image files provided");
        }

        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);
        authorizeTicketAccess(entity, uploadedBy, userEmail, otpToken);
        ensureAttachmentCapacity(entity.getId(), files.length);

        long maxAttachmentSize = supportProperties.getAttachment().getMaxSizeBytes();
        List<SupportTicketAttachmentDto> uploaded = new ArrayList<>();
        for (MultipartFile file : files) {
            if (file == null || file.isEmpty()) {
                continue;
            }
            if (file.getSize() > maxAttachmentSize) {
                throw new IllegalArgumentException(
                        "Attachment exceeds maximum size of " + (maxAttachmentSize / 1048576) + "MB");
            }

            AttachmentStorageProvider.UploadedImage image =
                    attachmentStorageProvider.uploadImage(file, entity.getUuid());
            SupportTicketAttachmentEntity saved = persistAttachment(
                    entity,
                    image.getFileName(),
                    image.getFileUrl(),
                    image.getFileSize(),
                    image.getMimeType(),
                    uploadedBy != null ? uploadedBy : "public");
            uploaded.add(mapToAttachment(saved));
        }

        if (uploaded.isEmpty()) {
            throw new IllegalArgumentException("No valid image files were uploaded");
        }
        return uploaded;
    }

    @Transactional
    public ApiResponse escalateTicket(String ticketId, String escalatedBy, String reason,
                                      String userEmail, String otpToken) {
        return escalateTicket(ticketId, escalatedBy, reason, userEmail, otpToken, false);
    }

    @Transactional
    public ApiResponse escalateTicket(String ticketId, String escalatedBy, String reason,
                                      String userEmail, String otpToken, boolean adminAccess) {
        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);
        if (!adminAccess) {
            authorizeTicketAccess(entity, escalatedBy, userEmail, otpToken);
        }

        String previousStatus = entity.getStatus();
        entity.setIsEscalated(true);
        entity.setEscalatedAt(new Date());
        entity.setEscalatedBy(escalatedBy);
        entity.setStatus("ESCALATED");
        ticketRepository.save(entity);

        recordStatusChange(entity.getId(), previousStatus, "ESCALATED", escalatedBy, escalatedBy, reason);
        auditLog(entity.getId(), "TICKET_ESCALATED", escalatedBy, escalatedBy, reason);
        notificationIntegrationService.notifyTicketEvent(entity, "TICKET_ESCALATED");

        return new ApiResponse(200, "success", "Ticket escalated", entity.getUuid());
    }

    @Transactional
    public ApiResponse assignTicket(String ticketId, String assignToId, String assignToName,
                                    String assignTeam, String assignedById, String assignedByName) {
        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);
        String previousStatus = entity.getStatus();

        entity.setAssignedAgentId(assignToId);
        entity.setAssignedAgentName(assignToName);
        entity.setAssignedTeam(assignTeam);
        if ("RECEIVED".equals(entity.getStatus()) || "SUBMITTED".equals(entity.getStatus())) {
            entity.setStatus("ASSIGNED");
            recordStatusChange(entity.getId(), previousStatus, "ASSIGNED", assignedById, assignedByName, null);
        }
        ticketRepository.save(entity);

        SupportTicketAssignmentHistoryEntity history = new SupportTicketAssignmentHistoryEntity();
        history.setTicketId(entity.getId());
        history.setAssignedToId(assignToId);
        history.setAssignedToName(assignToName);
        history.setAssignedTeam(assignTeam);
        history.setAssignedById(assignedById);
        history.setAssignedByName(assignedByName);
        assignmentHistoryRepository.save(history);

        auditLog(entity.getId(), "TICKET_ASSIGNED", assignedById, assignedByName,
                "Assigned to " + (assignToName != null ? assignToName : assignTeam));
        notificationIntegrationService.notifyTicketEvent(entity, "TICKET_ASSIGNED");

        return new ApiResponse(200, "success", "Ticket assigned", entity.getUuid());
    }

    @Transactional
    public ApiResponse updateTicket(UpdateSupportTicketInput input, String updatedBy, String updatedByName) {
        SupportTicketEntity entity = findTicketByIdOrUuid(input.getTicketId());
        String previousStatus = entity.getStatus();

        if (input.getStatus() != null) {
            String normalizedStatus = SupportCategoryCatalog.normalizeStatus(input.getStatus());
            if (VALID_STATUSES.contains(normalizedStatus)) {
                entity.setStatus(normalizedStatus);
                recordStatusChange(entity.getId(), previousStatus, entity.getStatus(), updatedBy, updatedByName, null);
                if (RESOLVED_STATUSES.contains(entity.getStatus())) {
                    slaRepository.findByTicketId(entity.getId()).ifPresent(sla -> {
                        sla.setResolvedAt(new Date());
                        slaRepository.save(sla);
                    });
                }
            }
        }
        if (input.getPriority() != null) {
            entity.setPriority(input.getPriority().toUpperCase());
        }
        if (input.getResolution() != null) {
            entity.setResolution(input.getResolution());
        }
        if (input.getCategory() != null) {
            entity.setCategory(SupportCategoryCatalog.normalizeCode(input.getCategory()));
        }
        if (input.getTags() != null) {
            entity.setTags(input.getTags());
        }

        entity.setModifiedBy(updatedBy);
        ticketRepository.save(entity);

        auditLog(entity.getId(), "TICKET_UPDATED", updatedBy, updatedByName, "Ticket updated");
        notificationIntegrationService.notifyTicketEvent(entity, "STATUS_CHANGED");

        return new ApiResponse(200, "success", "Ticket updated", entity.getUuid());
    }

    @Transactional
    public ApiResponse replyToTicket(String ticketId, String responseText, String agentId, String agentName) {
        SupportTicketEntity entity = findTicketByIdOrUuid(ticketId);

        addComment(ticketId, responseText, agentId, agentName, "AGENT", false, null, null);

        if (!"AWAITING_USER_RESPONSE".equals(entity.getStatus())) {
            String prev = entity.getStatus();
            entity.setStatus("AWAITING_USER_RESPONSE");
            ticketRepository.save(entity);
            recordStatusChange(entity.getId(), prev, "AWAITING_USER_RESPONSE", agentId, agentName, null);
        }

        slaRepository.findByTicketId(entity.getId()).ifPresent(sla -> {
            if (sla.getFirstResponseAt() == null) {
                sla.setFirstResponseAt(new Date());
                slaRepository.save(sla);
            }
        });

        notificationIntegrationService.notifyTicketEvent(entity, "AGENT_REPLY");
        return new ApiResponse(200, "success", "Reply sent", entity.getUuid());
    }

    @Transactional
    public ApiResponse bulkUpdateTickets(BulkUpdateSupportTicketInput input, String updatedBy, String updatedByName) {
        if (input.getTicketIds() == null || input.getTicketIds().isEmpty()) {
            return new ApiResponse(400, "error", "No ticket IDs provided", "");
        }

        int updated = 0;
        for (String ticketId : input.getTicketIds()) {
            UpdateSupportTicketInput single = new UpdateSupportTicketInput();
            single.setTicketId(ticketId);
            single.setStatus(input.getStatus());
            single.setPriority(input.getPriority());
            updateTicket(single, updatedBy, updatedByName);

            if (input.getAssignedAgentId() != null) {
                assignTicket(ticketId, input.getAssignedAgentId(), null,
                        input.getAssignedTeam(), updatedBy, updatedByName);
            }
            updated++;
        }

        return new ApiResponse(200, "success", updated + " tickets updated", "");
    }

    @Transactional
    public ApiResponse mergeTickets(String primaryTicketId, List<String> duplicateTicketIds,
                                    String mergedBy, String mergedByName) {
        SupportTicketEntity primary = findTicketByIdOrUuid(primaryTicketId);

        for (String dupId : duplicateTicketIds) {
            SupportTicketEntity dup = findTicketByIdOrUuid(dupId);
            List<SupportTicketCommentEntity> comments = commentRepository.findByTicketIdOrderByCreatedTsAsc(dup.getId());
            for (SupportTicketCommentEntity c : comments) {
                c.setTicketId(primary.getId());
                commentRepository.save(c);
            }
            dup.setIsDeleted(true);
            dup.setStatus("CLOSED");
            dup.setResolution("Merged into " + primary.getTicketNumber());
            ticketRepository.save(dup);
            auditLog(dup.getId(), "TICKET_MERGED", mergedBy, mergedByName,
                    "Merged into " + primary.getTicketNumber());
        }

        auditLog(primary.getId(), "TICKETS_MERGED", mergedBy, mergedByName,
                "Merged " + duplicateTicketIds.size() + " duplicate tickets");
        return new ApiResponse(200, "success", "Tickets merged", primary.getUuid());
    }

    private SupportTicketEntity findTicketByIdOrUuid(String ticketId) {
        Optional<SupportTicketEntity> byUuid = ticketRepository.findByUuid(ticketId);
        if (byUuid.isPresent()) {
            return byUuid.get();
        }
        Optional<SupportTicketEntity> byNumber = ticketRepository.findByTicketNumber(ticketId);
        if (byNumber.isPresent()) {
            return byNumber.get();
        }
        try {
            return ticketRepository.findById(Long.parseLong(ticketId))
                    .orElseThrow(() -> new NoSuchElementException("Ticket not found: " + ticketId));
        } catch (NumberFormatException e) {
            throw new NoSuchElementException("Ticket not found: " + ticketId);
        }
    }

    private void authorizeTicketAccess(SupportTicketEntity entity, String userId,
                                       String userEmail, String otpToken) {
        if (userId != null && userId.equals(entity.getParticipantUserId())) {
            return;
        }
        String normalizedUserEmail = normalizeEmail(userEmail);
        String normalizedParticipantEmail = normalizeEmail(entity.getParticipantEmail());
        if (normalizedUserEmail != null && normalizedUserEmail.equals(normalizedParticipantEmail)) {
            return;
        }
        if (otpToken != null) {
            String verifiedEmail = supportOtpService.validateSessionToken(otpToken);
            if (verifiedEmail != null
                    && normalizeEmail(verifiedEmail).equals(normalizedParticipantEmail)) {
                return;
            }
        }
        throw new SecurityException("Access denied to ticket");
    }

    private String normalizeEmail(String email) {
        if (email == null || email.trim().isEmpty()) {
            return null;
        }
        return email.trim().toLowerCase();
    }

    private void createSlaTracking(SupportTicketEntity ticket) {
        int defaultSlaHours = supportProperties.getSla().getDefaultHours();
        SupportSlaTrackingEntity sla = new SupportSlaTrackingEntity();
        sla.setTicketId(ticket.getId());
        sla.setSlaHours(defaultSlaHours);
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.HOUR, defaultSlaHours);
        sla.setDueAt(cal.getTime());
        slaRepository.save(sla);

        ticket.setSlaDueAt(sla.getDueAt());
        ticketRepository.save(ticket);
    }

    private void recordStatusChange(Long ticketId, String from, String to,
                                    String changedById, String changedByName, String notes) {
        SupportTicketStatusHistoryEntity history = new SupportTicketStatusHistoryEntity();
        history.setTicketId(ticketId);
        history.setFromStatus(from);
        history.setToStatus(to);
        history.setChangedById(changedById);
        history.setChangedByName(changedByName);
        history.setNotes(notes);
        statusHistoryRepository.save(history);
    }

    private void auditLog(Long ticketId, String action, String actorId, String actorName, String details) {
        SupportTicketAuditLogEntity logRecord = new SupportTicketAuditLogEntity();
        logRecord.setTicketId(ticketId);
        logRecord.setAction(action);
        logRecord.setActorId(actorId);
        logRecord.setActorName(actorName);
        logRecord.setDetails(details);
        auditLogRepository.save(logRecord);
    }

    private String generateTicketNumber() {
        int year = Calendar.getInstance().get(Calendar.YEAR);
        long count = ticketRepository.countTicketsThisYear() + 1;
        return String.format("SR-%d-%06d", year, count);
    }

    private SupportTicketCreatedResultDto mapCreatedResult(SupportTicketEntity ticket) {
        int defaultSlaHours = supportProperties.getSla().getDefaultHours();
        SupportTicketCreatedResultDto result = new SupportTicketCreatedResultDto();
        result.setTicketId(ticket.getUuid());
        result.setTicketNumber(ticket.getTicketNumber());
        result.setCreatedDate(formatDate(ticket.getCreatedTs()));
        result.setDisplayCreatedDate(formatDisplayDate(ticket.getCreatedTs()));
        result.setStatus(ticket.getStatus());
        result.setDisplayStatus(SupportCategoryCatalog.toDisplayStatus(ticket.getStatus()));
        result.setSlaHours(defaultSlaHours);
        result.setExpectedResponseText(buildExpectedResponseText(defaultSlaHours));
        return result;
    }

    private String resolveParticipantEmail(String userId, String jwtEmail, String inputEmail) {
        if (jwtEmail != null && !jwtEmail.trim().isEmpty()) {
            return normalizeEmail(jwtEmail);
        }
        if (inputEmail != null && !inputEmail.trim().isEmpty()) {
            return normalizeEmail(inputEmail);
        }
        return null;
    }

    private String buildExpectedResponseText(int slaHours) {
        if (slaHours <= 24) {
            return "Expected response within 24 Hours";
        }
        return "Expected response within " + slaHours + " Hours";
    }

    private void ensureAttachmentCapacity(Long ticketId, int incomingCount) {
        long existing = attachmentRepository.countByTicketIdAndIsDeletedFalse(ticketId);
        int maxCount = supportProperties.getAttachment().getMaxCount();
        if (existing + incomingCount > maxCount) {
            throw new IllegalArgumentException("A maximum of " + maxCount + " images are allowed per ticket");
        }
    }

    private void linkStagedAttachments(SupportTicketEntity ticket,
                                       List<SupportAttachmentRefInput> attachments,
                                       String uploadedBy) {
        if (attachments == null || attachments.isEmpty()) {
            return;
        }
        int maxCount = supportProperties.getAttachment().getMaxCount();
        if (attachments.size() > maxCount) {
            throw new IllegalArgumentException("A maximum of " + maxCount + " images are allowed per ticket");
        }

        ensureAttachmentCapacity(ticket.getId(), attachments.size());

        long maxAttachmentSize = supportProperties.getAttachment().getMaxSizeBytes();
        for (SupportAttachmentRefInput ref : attachments) {
            AttachmentStorageProvider.StagedImageRef staged = attachmentStorageProvider.resolveStagedAttachment(
                    ref.getFileId(), ref.getFileName(), ref.getFileSize(), ref.getMimeType());

            if (staged.getFileSize() != null && staged.getFileSize() > maxAttachmentSize) {
                throw new IllegalArgumentException(
                        "Attachment exceeds maximum size of " + (maxAttachmentSize / 1048576) + "MB");
            }

            persistAttachment(ticket, staged.getFileName(), staged.getFileUrl(),
                    staged.getFileSize(), staged.getMimeType(), uploadedBy);
        }
    }

    private SupportTicketAttachmentEntity persistAttachment(SupportTicketEntity entity, String fileName,
                                                            String fileUrl, Long fileSizeBytes,
                                                            String mimeType, String uploadedBy) {
        SupportTicketAttachmentEntity attachment = new SupportTicketAttachmentEntity();
        attachment.setTicketId(entity.getId());
        attachment.setFileName(fileName);
        attachment.setFileUrl(fileUrl);
        attachment.setFileSize(fileSizeBytes);
        attachment.setMimeType(mimeType);
        attachment.setScanStatus("CLEAN");
        attachment.setUploadedBy(uploadedBy);
        attachmentRepository.save(attachment);
        auditLog(entity.getId(), "ATTACHMENT_UPLOADED", uploadedBy, uploadedBy, fileName);
        return attachment;
    }

    private SupportTicketDetailDto buildTicketDetail(SupportTicketEntity entity, boolean includeInternal) {
        SupportTicketDetailDto detail = new SupportTicketDetailDto();
        detail.setTicket(mapToTicket(entity));
        detail.setResolution(entity.getResolution());
        detail.setAssignedAgent(entity.getAssignedAgentName());

        List<SupportTicketCommentEntity> comments = includeInternal
                ? commentRepository.findByTicketIdOrderByCreatedTsAsc(entity.getId())
                : commentRepository.findByTicketIdAndIsInternalFalseOrderByCreatedTsAsc(entity.getId());
        detail.setConversationHistory(comments.stream().map(this::mapToComment).collect(Collectors.toList()));

        detail.setAttachments(attachmentRepository.findByTicketIdOrderByCreatedTsAsc(entity.getId())
                .stream().map(this::mapToAttachment).collect(Collectors.toList()));

        detail.setInternalStatus(entity.getStatus());
        detail.setSla(buildSlaInfo(entity.getId()));
        detail.setTimeline(buildTimeline(entity, includeInternal));
        if (includeInternal) {
            detail.setAuditTimeline(auditLogRepository.findByTicketIdOrderByCreatedTsAsc(entity.getId())
                    .stream().map(this::mapToAudit).collect(Collectors.toList()));
        }

        return detail;
    }

    private List<SupportTimelineEventDto> buildTimeline(SupportTicketEntity entity, boolean includeInternal) {
        List<SupportTimelineEventDto> events = new ArrayList<>();

        SupportTimelineEventDto created = new SupportTimelineEventDto();
        created.setEventType("TICKET_CREATED");
        created.setTitle("Ticket Created");
        created.setCreatedTs(formatDate(entity.getCreatedTs()));
        created.setStatus(entity.getStatus());
        created.setDisplayStatus(SupportCategoryCatalog.toDisplayStatus(entity.getStatus()));
        events.add(created);

        for (SupportTicketAssignmentHistoryEntity assignment :
                assignmentHistoryRepository.findByTicketIdOrderByCreatedTsAsc(entity.getId())) {
            SupportTimelineEventDto assigned = new SupportTimelineEventDto();
            assigned.setEventType("ASSIGNED");
            assigned.setTitle("Assigned to Agent");
            String agentName = assignment.getAssignedToName() != null
                    ? assignment.getAssignedToName()
                    : assignment.getAssignedTeam();
            assigned.setActorName(agentName);
            assigned.setMessage(agentName != null
                    ? agentName + " is reviewing your request."
                    : "Your request has been assigned to support.");
            assigned.setCreatedTs(formatDate(assignment.getCreatedTs()));
            events.add(assigned);
        }

        List<SupportTicketCommentEntity> comments = includeInternal
                ? commentRepository.findByTicketIdOrderByCreatedTsAsc(entity.getId())
                : commentRepository.findByTicketIdAndIsInternalFalseOrderByCreatedTsAsc(entity.getId());
        for (SupportTicketCommentEntity comment : comments) {
            SupportTimelineEventDto event = new SupportTimelineEventDto();
            event.setCommentId(comment.getUuid());
            event.setActorName(comment.getAuthorName());
            event.setMessage(comment.getCommentText());
            event.setCreatedTs(formatDate(comment.getCreatedTs()));
            if ("AGENT".equalsIgnoreCase(comment.getAuthorType())) {
                event.setEventType("AGENT_REPLY");
                event.setTitle("Response Required");
                event.setStatus("AWAITING_USER_RESPONSE");
                event.setDisplayStatus(SupportCategoryCatalog.toDisplayStatus("AWAITING_USER_RESPONSE"));
            } else {
                event.setEventType("USER_REPLY");
                event.setTitle("Your Reply");
            }
            events.add(event);
        }

        for (SupportTicketStatusHistoryEntity statusChange :
                statusHistoryRepository.findByTicketIdOrderByCreatedTsAsc(entity.getId())) {
            SupportTimelineEventDto event = new SupportTimelineEventDto();
            event.setEventType("STATUS_CHANGE");
            event.setTitle("Status Changed");
            event.setStatus(statusChange.getToStatus());
            event.setDisplayStatus(SupportCategoryCatalog.toDisplayStatus(statusChange.getToStatus()));
            event.setMessage(statusChange.getNotes());
            event.setActorName(statusChange.getChangedByName());
            event.setCreatedTs(formatDate(statusChange.getCreatedTs()));
            events.add(event);
        }

        events.sort(Comparator.comparing(SupportTimelineEventDto::getCreatedTs,
                Comparator.nullsLast(Comparator.naturalOrder())));
        return events;
    }

    private SupportSlaInfoDto buildSlaInfo(Long ticketId) {
        return slaRepository.findByTicketId(ticketId).map(sla -> {
            SupportSlaInfoDto info = new SupportSlaInfoDto();
            info.setSlaHours(sla.getSlaHours());
            info.setDueAt(formatDate(sla.getDueAt()));
            info.setFirstResponseAt(formatDate(sla.getFirstResponseAt()));
            info.setResolvedAt(formatDate(sla.getResolvedAt()));
            info.setBreached(sla.getBreached());
            if (sla.getDueAt() != null) {
                long diff = sla.getDueAt().getTime() - System.currentTimeMillis();
                info.setRemainingMinutes((int) Math.max(0, diff / 60000));
            }
            info.setExpectedResponseText(buildExpectedResponseText(sla.getSlaHours()));
            return info;
        }).orElse(null);
    }

    private SupportAuditEntryDto mapToAudit(SupportTicketAuditLogEntity entity) {
        SupportAuditEntryDto dto = new SupportAuditEntryDto();
        dto.setAction(entity.getAction());
        dto.setActorId(entity.getActorId());
        dto.setActorName(entity.getActorName());
        dto.setDetails(entity.getDetails());
        dto.setCreatedTs(formatDate(entity.getCreatedTs()));
        return dto;
    }

    private SupportTicketDto mapToTicket(SupportTicketEntity entity) {
        SupportTicketDto dto = new SupportTicketDto();
        dto.setTicketId(entity.getUuid());
        dto.setTicketNumber(entity.getTicketNumber());
        dto.setSubject(entity.getSubject());
        dto.setCategory(entity.getCategory());
        dto.setStatus(entity.getStatus());
        dto.setPriority(entity.getPriority());
        dto.setAssignedAgent(entity.getAssignedAgentName());
        dto.setAssignedAgentId(entity.getAssignedAgentId());
        dto.setAssignedTeam(entity.getAssignedTeam());
        dto.setParticipantEmail(entity.getParticipantEmail());
        dto.setParticipantUserId(entity.getParticipantUserId());
        dto.setStudyId(entity.getStudyId());
        dto.setResolution(entity.getResolution());
        dto.setTags(entity.getTags());
        dto.setIsEscalated(entity.getIsEscalated());
        dto.setCreatedDate(formatDate(entity.getCreatedTs()));
        dto.setUpdatedDate(formatDate(entity.getModifiedTs()));
        dto.setSlaDueAt(formatDate(entity.getSlaDueAt()));
        dto.setSlaBreached(entity.getSlaBreached());
        dto.setDescription(entity.getDescription());
        dto.setDiagnosticsJson(entity.getDiagnosticsJson());
        dto.setPrivacyAccepted(entity.getPrivacyAccepted());
        dto.setDisplayStatus(SupportCategoryCatalog.toDisplayStatus(entity.getStatus()));
        dto.setCategoryLabel(SupportCategoryCatalog.labelFor(entity.getCategory()));
        return dto;
    }

    private SupportTicketCommentDto mapToComment(SupportTicketCommentEntity entity) {
        SupportTicketCommentDto dto = new SupportTicketCommentDto();
        dto.setCommentId(entity.getUuid());
        dto.setAuthorId(entity.getAuthorId());
        dto.setAuthorName(entity.getAuthorName());
        dto.setAuthorType(entity.getAuthorType());
        dto.setCommentText(entity.getCommentText());
        dto.setIsInternal(entity.getIsInternal());
        dto.setCreatedTs(formatDate(entity.getCreatedTs()));
        return dto;
    }

    private SupportTicketAttachmentDto mapToAttachment(SupportTicketAttachmentEntity entity) {
        SupportTicketAttachmentDto dto = new SupportTicketAttachmentDto();
        dto.setAttachmentId(entity.getUuid());
        dto.setFileName(entity.getFileName());
        dto.setFileUrl(attachmentStorageProvider.generatePresignedDownloadUrl(entity.getFileUrl()));
        dto.setFileSize(entity.getFileSize() != null ? entity.getFileSize().intValue() : null);
        dto.setMimeType(entity.getMimeType());
        dto.setScanStatus(entity.getScanStatus());
        dto.setUploadedBy(entity.getUploadedBy());
        dto.setCreatedTs(formatDate(entity.getCreatedTs()));
        return dto;
    }

    private List<SupportTicketEntity> findAccessibleParticipantTickets(String userId, String userEmail) {
        Map<Long, SupportTicketEntity> byId = new LinkedHashMap<>();
        if (userId != null && !userId.trim().isEmpty()) {
            for (SupportTicketEntity ticket : ticketRepository.findByParticipantUserIdOrderByCreatedTsDesc(userId)) {
                byId.put(ticket.getId(), ticket);
            }
        }
        if (userEmail != null && !userEmail.trim().isEmpty()) {
            String normalizedEmail = normalizeEmail(userEmail);
            for (SupportTicketEntity ticket : ticketRepository.findByParticipantEmailIgnoreCaseOrderByCreatedTsDesc(normalizedEmail)) {
                byId.put(ticket.getId(), ticket);
            }
        }
        List<SupportTicketEntity> entities = new ArrayList<>(byId.values());
        entities.sort(Comparator.comparing(SupportTicketEntity::getCreatedTs,
                Comparator.nullsLast(Comparator.reverseOrder())));
        return entities;
    }

    private List<SupportTicketEntity> applyInMemoryFilters(List<SupportTicketEntity> entities,
                                                           SupportTicketFilterInput filter) {
        if (filter == null) {
            return entities;
        }
        return entities.stream().filter(t -> {
            if (filter.getStatus() != null && !filter.getStatus().trim().isEmpty()) {
                String normalizedFilterStatus = SupportCategoryCatalog.normalizeStatus(filter.getStatus());
                String normalizedTicketStatus = SupportCategoryCatalog.normalizeStatus(t.getStatus());
                if (!normalizedFilterStatus.equalsIgnoreCase(normalizedTicketStatus)) {
                    return false;
                }
            }
            if (filter.getCategory() != null && !filter.getCategory().equalsIgnoreCase(t.getCategory())) {
                return false;
            }
            if (filter.getPriority() != null && !filter.getPriority().equalsIgnoreCase(t.getPriority())) {
                return false;
            }
            if (filter.getSearchText() != null && !filter.getSearchText().trim().isEmpty()) {
                String query = filter.getSearchText().trim().toLowerCase();
                boolean matchSubject = t.getSubject() != null && t.getSubject().toLowerCase().contains(query);
                boolean matchNumber = t.getTicketNumber() != null && t.getTicketNumber().toLowerCase().contains(query);
                boolean matchDesc = t.getDescription() != null && t.getDescription().toLowerCase().contains(query);
                if (!matchSubject && !matchNumber && !matchDesc) {
                    return false;
                }
            }
            return true;
        }).collect(Collectors.toList());
    }

    private SupportTicketListResultDto paginateAndMap(List<SupportTicketEntity> entities,
                                                      SupportPaginationInput pagination,
                                                      SupportSortInput sort) {
        int page = pagination != null && pagination.getPage() != null ? pagination.getPage() : 0;
        int size = pagination != null && pagination.getPageSize() != null ? pagination.getPageSize() : 20;

        if (sort != null && sort.getField() != null) {
            boolean asc = "ASC".equalsIgnoreCase(sort.getDirection());
            if ("createdTs".equals(sort.getField())) {
                entities.sort(Comparator.comparing(SupportTicketEntity::getCreatedTs,
                        asc ? Comparator.nullsLast(Comparator.naturalOrder())
                                : Comparator.nullsLast(Comparator.reverseOrder())));
            }
        }

        int fromIndex = Math.min(page * size, entities.size());
        int toIndex = Math.min(fromIndex + size, entities.size());
        List<SupportTicketEntity> sublist = entities.subList(fromIndex, toIndex);

        SupportTicketListResultDto result = new SupportTicketListResultDto();
        result.setTickets(sublist.stream().map(this::mapToTicket).collect(Collectors.toList()));
        result.setTotalCount(entities.size());
        result.setPage(page);
        result.setPageSize(size);
        return result;
    }

    private Specification<SupportTicketEntity> buildSpecification(SupportTicketFilterInput filter) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();
            if (filter == null) {
                return cb.and(predicates.toArray(new Predicate[0]));
            }
            if (filter.getStatus() != null && !filter.getStatus().trim().isEmpty()) {
                predicates.add(cb.equal(root.get("status"), SupportCategoryCatalog.normalizeStatus(filter.getStatus())));
            }
            if (filter.getCategory() != null && !filter.getCategory().trim().isEmpty()) {
                predicates.add(cb.equal(root.get("category"), SupportCategoryCatalog.normalizeCode(filter.getCategory())));
            }
            if (filter.getPriority() != null && !filter.getPriority().trim().isEmpty()) {
                predicates.add(cb.equal(root.get("priority"), filter.getPriority().toUpperCase()));
            }
            if (filter.getSearchText() != null && !filter.getSearchText().trim().isEmpty()) {
                String pattern = "%" + filter.getSearchText().trim().toLowerCase() + "%";
                predicates.add(cb.or(
                        cb.like(cb.lower(root.get("subject")), pattern),
                        cb.like(cb.lower(root.get("ticketNumber")), pattern),
                        cb.like(cb.lower(root.get("description")), pattern)
                ));
            }
            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }

    private String mapSortField(String field) {
        switch (field) {
            case "ticketNumber": return "ticketNumber";
            case "status": return "status";
            case "priority": return "priority";
            case "subject": return "subject";
            default: return "createdTs";
        }
    }

    private String formatDate(Date date) {
        if (date == null) return null;
        return new SimpleDateFormat(DATETIME_FORMAT).format(date);
    }

    private String formatDisplayDate(Date date) {
        if (date == null) return null;
        return new SimpleDateFormat(DISPLAY_DATETIME_FORMAT).format(date);
    }
}
