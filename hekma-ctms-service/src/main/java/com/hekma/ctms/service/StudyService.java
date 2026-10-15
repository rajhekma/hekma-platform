package com.hekma.ctms.service;

import com.hekma.ctms.domain.*;
import com.hekma.ctms.dto.StudyRequest;
import com.hekma.ctms.dto.StudyResponse;
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
public class StudyService {

    private final StudyRepository studyRepository;
    private final StudyArmRepository studyArmRepository;
    private final StudyArmDetailRepository studyArmDetailRepository;
    private final StudyEventRepository studyEventRepository;
    private final StudyContactRepository studyContactRepository;

    @Transactional
    public StudyResponse createStudy(StudyRequest req, CtmsPrincipal principal) {
        String studyId = UUID.randomUUID().toString();
        String studyNumber = req.getStudyNumber() != null ? req.getStudyNumber() : "STD-" + System.currentTimeMillis();

        StudyEntity entity = StudyEntity.builder()
                .studyId(studyId)
                .studyNumber(studyNumber)
                .protocolNumber(req.getProtocolNumber())
                .parentAccountId(req.getParentAccountId())
                .studyTitle(req.getStudyTitle())
                .nameOfImp(req.getNameOfImp())
                .devPhase(req.getDevPhase())
                .status(req.getStatus() != null ? req.getStatus() : "DRAFT")
                .primaryEndPoint(req.getPrimaryEndPoint())
                .secondaryEndPoint(req.getSecondaryEndPoint())
                .expEndPoint(req.getExpEndPoint())
                .startDate(req.getStartDate())
                .endDate(req.getEndDate())
                .studyDuration(req.getStudyDuration())
                .stoppingCriteria(req.getStoppingCriteria())
                .numberOfSitesPlanned(req.getNumberOfSitesPlanned())
                .numberOfSubPlanned(req.getNumberOfSubPlanned())
                .route(req.getRoute())
                .regiman(req.getRegiman())
                .dosage(req.getDosage())
                .statMethod(req.getStatMethod())
                .interimAnalysis(req.getInterimAnalysis())
                .studyFlow(req.getStudyFlow())
                .studyStatus(req.getStudyStatus())
                .studyType(req.getStudyType())
                .studyPhase(req.getStudyPhase())
                .sponsorType(req.getSponsorType())
                .indication(req.getIndication())
                .therapeuticArea(req.getTherapeuticArea())
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();

        StudyEntity saved = studyRepository.save(entity);
        log.info("Study created successfully: id={}, studyNumber={}", saved.getId(), saved.getStudyNumber());
        return StudyResponse.fromEntity(saved);
    }

    @Transactional
    public StudyResponse updateStudy(String studyId, StudyRequest req, CtmsPrincipal principal) {
        StudyEntity entity = getStudyEntity(studyId);
        assertWithinSubtree(entity, principal);

        if (req.getStudyTitle() != null) entity.setStudyTitle(req.getStudyTitle());
        if (req.getStatus() != null) entity.setStatus(req.getStatus());
        if (req.getNameOfImp() != null) entity.setNameOfImp(req.getNameOfImp());
        if (req.getDevPhase() != null) entity.setDevPhase(req.getDevPhase());
        if (req.getPrimaryEndPoint() != null) entity.setPrimaryEndPoint(req.getPrimaryEndPoint());
        if (req.getSecondaryEndPoint() != null) entity.setSecondaryEndPoint(req.getSecondaryEndPoint());
        if (req.getExpEndPoint() != null) entity.setExpEndPoint(req.getExpEndPoint());
        if (req.getStartDate() != null) entity.setStartDate(req.getStartDate());
        if (req.getEndDate() != null) entity.setEndDate(req.getEndDate());
        if (req.getStoppingCriteria() != null) entity.setStoppingCriteria(req.getStoppingCriteria());
        if (req.getIndication() != null) entity.setIndication(req.getIndication());
        if (req.getTherapeuticArea() != null) entity.setTherapeuticArea(req.getTherapeuticArea());

        StudyEntity saved = studyRepository.save(entity);
        log.info("Study updated successfully: studyId={}", studyId);
        return StudyResponse.fromEntity(saved);
    }

    @Transactional(readOnly = true)
    public StudyResponse getStudy(String studyId, CtmsPrincipal principal) {
        StudyEntity entity = getStudyEntity(studyId);
        assertWithinSubtree(entity, principal);
        return StudyResponse.fromEntity(entity);
    }

    @Transactional(readOnly = true)
    public List<StudyResponse> listStudies(CtmsPrincipal principal) {
        List<StudyEntity> list;
        if (principal == null || principal.isPlatformAdmin() || principal.tenantPath() == null) {
            list = studyRepository.findAll();
        } else {
            list = studyRepository.findByTenantPathStartingWith(principal.tenantPath());
        }
        return list.stream().map(StudyResponse::fromEntity).toList();
    }

    @Transactional(readOnly = true)
    public List<StudyResponse> searchStudies(String searchStr, CtmsPrincipal principal) {
        List<StudyResponse> all = listStudies(principal);
        if (searchStr == null || searchStr.isBlank() || "*".equals(searchStr)) {
            return all;
        }
        String lower = searchStr.toLowerCase();
        return all.stream()
                .filter(s -> (s.getStudyTitle() != null && s.getStudyTitle().toLowerCase().contains(lower)) ||
                        (s.getStudyNumber() != null && s.getStudyNumber().toLowerCase().contains(lower)) ||
                        (s.getIndication() != null && s.getIndication().toLowerCase().contains(lower)))
                .toList();
    }

    public StudyEntity getStudyEntity(String studyId) {
        return studyRepository.findByStudyId(studyId)
                .or(() -> studyRepository.findByStudyNumber(studyId))
                .orElseThrow(() -> new ResourceNotFoundException("Study not found with identifier: " + studyId));
    }

    private void assertWithinSubtree(StudyEntity entity, CtmsPrincipal principal) {
        if (principal != null && !principal.isWithinSubtree(entity.getTenantPath())) {
            throw new AccessDeniedException("Access denied: study is outside of your organization scope.");
        }
    }

    // --- Arms ---
    @Transactional
    public StudyArmEntity addStudyArm(String armName, String studyId, String type, String description, String status, CtmsPrincipal principal) {
        String armNum = "ARM-" + System.currentTimeMillis();
        StudyArmEntity arm = StudyArmEntity.builder()
                .armNum(armNum)
                .studyId(studyId)
                .armName(armName)
                .armType(type)
                .description(description)
                .status(status != null ? status : "ACTIVE")
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();
        return studyArmRepository.save(arm);
    }

    @Transactional(readOnly = true)
    public List<StudyArmEntity> getStudyArms(String studyId) {
        return studyArmRepository.findByStudyId(studyId);
    }

    @Transactional(readOnly = true)
    public List<StudyArmDetailEntity> getStudyArmDetails(String armNum) {
        return studyArmDetailRepository.findByArmNum(armNum);
    }

    @Transactional
    public void deleteStudyArm(String armNum) {
        studyArmRepository.findByArmNum(armNum).ifPresent(studyArmRepository::delete);
    }

    // --- Events ---
    @Transactional
    public StudyEventEntity createStudyEvent(String studyId, String eventType, String type, String description, String severity, String status, String effectiveDate, CtmsPrincipal principal) {
        String eventId = UUID.randomUUID().toString();
        StudyEventEntity event = StudyEventEntity.builder()
                .eventId(eventId)
                .studyId(studyId)
                .eventType(eventType)
                .subType(type)
                .description(description)
                .severity(severity)
                .status(status != null ? status : "ACTIVE")
                .effectiveDate(effectiveDate)
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();
        return studyEventRepository.save(event);
    }

    @Transactional(readOnly = true)
    public List<StudyEventEntity> getStudyEvents(String studyId, String eventType) {
        if (eventType == null || "*".equals(eventType) || eventType.isBlank()) {
            return studyEventRepository.findByStudyId(studyId);
        }
        return studyEventRepository.findByStudyIdAndEventType(studyId, eventType);
    }

    @Transactional
    public void deleteStudyEvent(String eventId) {
        studyEventRepository.findByEventId(eventId).ifPresent(studyEventRepository::delete);
    }

    // --- Contacts ---
    @Transactional
    public StudyContactEntity addStudyContact(String studyId, String contactId, String role, CtmsPrincipal principal) {
        StudyContactEntity contact = StudyContactEntity.builder()
                .studyId(studyId)
                .contactId(contactId)
                .role(role)
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();
        return studyContactRepository.save(contact);
    }

    @Transactional(readOnly = true)
    public List<StudyContactEntity> getStudyContacts(String studyId) {
        return studyContactRepository.findByStudyId(studyId);
    }

    @Transactional
    public void deleteStudyContact(String studyId, String contactId) {
        studyContactRepository.findByStudyIdAndContactId(studyId, contactId).ifPresent(studyContactRepository::delete);
    }
}
