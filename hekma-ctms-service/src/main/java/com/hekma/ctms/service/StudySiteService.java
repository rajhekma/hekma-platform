package com.hekma.ctms.service;

import com.hekma.ctms.domain.*;
import com.hekma.ctms.dto.*;
import com.hekma.ctms.exception.ResourceNotFoundException;
import com.hekma.ctms.repository.*;
import com.hekma.ctms.security.CtmsPrincipal;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class StudySiteService {

    private final StudySiteRepository studySiteRepository;
    private final StudySiteContactRepository studySiteContactRepository;
    private final StudySiteQueryRepository studySiteQueryRepository;
    private final StudySiteNoteRepository studySiteNoteRepository;
    private final StudyPagRepository studyPagRepository;

    @Transactional
    public StudySiteResponse addStudySite(StudySiteRequest req, CtmsPrincipal principal) {
        StudySiteEntity entity = StudySiteEntity.builder()
                .studyId(req.getStudyId())
                .siteId(req.getSiteId())
                .siteName(req.getSiteName())
                .siteUserId(req.getSiteUserId())
                .status(req.getStatus() != null ? req.getStatus() : "ACTIVE")
                .onboardStatus(req.getOnboardStatus() != null ? req.getOnboardStatus() : "NOT_STARTED")
                .limitization(req.getLimitization())
                .primaryContact(req.getPrimaryContact())
                .role(req.getRole())
                .impReceived(req.getImpReceived())
                .placeholder(req.getPlaceholder())
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();

        StudySiteEntity saved = studySiteRepository.save(entity);
        log.info("Site added to study: studyId={}, siteId={}", saved.getStudyId(), saved.getSiteId());
        return StudySiteResponse.fromEntity(saved);
    }

    @Transactional
    public StudySiteResponse updateStudySite(StudySiteRequest req, CtmsPrincipal principal) {
        StudySiteEntity entity = studySiteRepository.findByStudyIdAndSiteId(req.getStudyId(), req.getSiteId())
                .orElseThrow(() -> new ResourceNotFoundException("Study site link not found: " + req.getStudyId() + ", " + req.getSiteId()));

        if (req.getSiteName() != null) entity.setSiteName(req.getSiteName());
        if (req.getStatus() != null) entity.setStatus(req.getStatus());
        if (req.getOnboardStatus() != null) entity.setOnboardStatus(req.getOnboardStatus());
        if (req.getLimitization() != null) entity.setLimitization(req.getLimitization());
        if (req.getPrimaryContact() != null) entity.setPrimaryContact(req.getPrimaryContact());
        if (req.getRole() != null) entity.setRole(req.getRole());
        if (req.getImpReceived() != null) entity.setImpReceived(req.getImpReceived());

        return StudySiteResponse.fromEntity(studySiteRepository.save(entity));
    }

    @Transactional(readOnly = true)
    public List<StudySiteResponse> getStudySites(String studyId) {
        return studySiteRepository.findByStudyId(studyId).stream()
                .map(StudySiteResponse::fromEntity)
                .toList();
    }

    @Transactional(readOnly = true)
    public StudySiteResponse getStudySite(String studyId, String siteId) {
        return studySiteRepository.findByStudyIdAndSiteId(studyId, siteId)
                .map(StudySiteResponse::fromEntity)
                .orElseThrow(() -> new ResourceNotFoundException("Site not associated with study: " + studyId + ", site: " + siteId));
    }

    // --- Contacts ---
    @Transactional
    public StudySiteContactEntity addStudySiteContact(String studyId, String siteId, String contactId, String role, String primaryInd) {
        StudySiteContactEntity contact = StudySiteContactEntity.builder()
                .studyId(studyId)
                .siteId(siteId)
                .contactId(contactId)
                .role(role)
                .primaryContactInd(primaryInd)
                .build();
        return studySiteContactRepository.save(contact);
    }

    @Transactional(readOnly = true)
    public List<StudySiteContactEntity> getStudySiteContacts(String studyId, String siteId) {
        return studySiteContactRepository.findByStudyIdAndSiteId(studyId, siteId);
    }

    @Transactional
    public void deleteStudySiteContact(String studyId, String siteId, String contactId) {
        studySiteContactRepository.findByStudyIdAndSiteIdAndContactId(studyId, siteId, contactId)
                .ifPresent(studySiteContactRepository::delete);
    }

    // --- Queries ---
    @Transactional
    public StudyQueryResponse addStudySiteQuery(StudyQueryRequest req, CtmsPrincipal principal) {
        String queryId = req.getQueryId() != null ? req.getQueryId() : UUID.randomUUID().toString();
        String queryNum = req.getQueryNum() != null ? req.getQueryNum() : "QRY-" + System.currentTimeMillis();

        StudySiteQueryEntity query = StudySiteQueryEntity.builder()
                .queryId(queryId)
                .queryNum(queryNum)
                .studyId(req.getStudyId())
                .studyName(req.getStudyName())
                .siteId(req.getSiteId())
                .queryTitle(req.getQueryTitle())
                .queryDescription(req.getQueryDescription())
                .category(req.getCategory())
                .severity(req.getSeverity())
                .status("OPEN")
                .assignedTo(req.getAssignedTo())
                .assignedToName(req.getAssignedToName())
                .sponsorReference1(req.getSponsorReference1())
                .sponsorReference2(req.getSponsorReference2())
                .siteReference1(req.getSiteReference1())
                .siteReference2(req.getSiteReference2())
                .createdByName(principal != null ? principal.email() : "system")
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();

        return StudyQueryResponse.fromEntity(studySiteQueryRepository.save(query));
    }

    @Transactional
    public StudyQueryResponse resolveStudySiteQuery(String queryId) {
        StudySiteQueryEntity query = studySiteQueryRepository.findByQueryId(queryId)
                .orElseThrow(() -> new ResourceNotFoundException("Query not found: " + queryId));
        query.setStatus("RESOLVED");
        return StudyQueryResponse.fromEntity(studySiteQueryRepository.save(query));
    }

    @Transactional
    public StudyQueryResponse updateStudySiteQueryStatus(String queryId, String status) {
        StudySiteQueryEntity query = studySiteQueryRepository.findByQueryId(queryId)
                .orElseThrow(() -> new ResourceNotFoundException("Query not found: " + queryId));
        query.setStatus(status);
        return StudyQueryResponse.fromEntity(studySiteQueryRepository.save(query));
    }

    @Transactional(readOnly = true)
    public List<StudyQueryResponse> getStudySiteQueries(String studyId, String siteId) {
        return studySiteQueryRepository.findByStudyIdAndSiteId(studyId, siteId).stream()
                .map(StudyQueryResponse::fromEntity)
                .toList();
    }

    @Transactional(readOnly = true)
    public StudyQueryResponse getStudySiteQuery(String queryId) {
        return studySiteQueryRepository.findByQueryId(queryId)
                .map(StudyQueryResponse::fromEntity)
                .orElseThrow(() -> new ResourceNotFoundException("Query not found: " + queryId));
    }

    // --- Notes ---
    @Transactional
    public StudySiteNoteEntity createStudySiteNote(String studyId, String siteId, String title, String notes, String noteType, CtmsPrincipal principal) {
        String noteId = UUID.randomUUID().toString();
        StudySiteNoteEntity note = StudySiteNoteEntity.builder()
                .noteId(noteId)
                .studyId(studyId)
                .siteId(siteId)
                .title(title)
                .notes(notes)
                .noteType(noteType)
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();
        return studySiteNoteRepository.save(note);
    }

    @Transactional(readOnly = true)
    public List<StudySiteNoteEntity> getStudySiteNotes(String studyId, String siteId) {
        return studySiteNoteRepository.findByStudyIdAndSiteId(studyId, siteId);
    }

    @Transactional
    public void deleteStudySiteNote(String noteId) {
        studySiteNoteRepository.findByNoteId(noteId).ifPresent(studySiteNoteRepository::delete);
    }

    // --- PAG ---
    @Transactional
    public StudyPagEntity addStudyPag(String studyId, String pagId, String status, CtmsPrincipal principal) {
        StudyPagEntity pag = StudyPagEntity.builder()
                .studyId(studyId)
                .pagId(pagId)
                .status(status != null ? status : "ACTIVE")
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();
        return studyPagRepository.save(pag);
    }

    @Transactional(readOnly = true)
    public List<StudyPagEntity> getStudyPags(String studyId) {
        return studyPagRepository.findByStudyId(studyId);
    }
}
