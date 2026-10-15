package com.hekma.ctms.service;

import com.hekma.ctms.domain.StudyPatientAdverseEventEntity;
import com.hekma.ctms.dto.AdverseEventRequest;
import com.hekma.ctms.dto.AdverseEventResponse;
import com.hekma.ctms.exception.ResourceNotFoundException;
import com.hekma.ctms.repository.StudyPatientAdverseEventRepository;
import com.hekma.ctms.security.CtmsPrincipal;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class AdverseEventService {

    private final StudyPatientAdverseEventRepository adverseEventRepository;

    @Transactional
    public AdverseEventResponse createAdverseEvent(AdverseEventRequest req, CtmsPrincipal principal) {
        String adverseEventId = req.getAdverseEventId() != null ? req.getAdverseEventId() : UUID.randomUUID().toString();

        StudyPatientAdverseEventEntity entity = StudyPatientAdverseEventEntity.builder()
                .adverseEventId(adverseEventId)
                .studyId(req.getStudyId())
                .siteId(req.getSiteId())
                .patientId(req.getPatientId())
                .aeTerm(req.getAeTerm())
                .severity(req.getSeverity())
                .causality(req.getCausality())
                .outcome(req.getOutcome())
                .startDate(req.getStartDate())
                .stopDate(req.getStopDate())
                .summary(req.getSummary())
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();

        StudyPatientAdverseEventEntity saved = adverseEventRepository.save(entity);
        log.info("Adverse event recorded: aeId={}, studyId={}, siteId={}", saved.getAdverseEventId(), saved.getStudyId(), saved.getSiteId());
        return AdverseEventResponse.fromEntity(saved);
    }

    @Transactional
    public AdverseEventResponse updateAdverseEvent(String aeId, AdverseEventRequest req, CtmsPrincipal principal) {
        StudyPatientAdverseEventEntity entity = adverseEventRepository.findByAdverseEventId(aeId)
                .orElseThrow(() -> new ResourceNotFoundException("Adverse event not found: " + aeId));

        if (req.getAeTerm() != null) entity.setAeTerm(req.getAeTerm());
        if (req.getSeverity() != null) entity.setSeverity(req.getSeverity());
        if (req.getCausality() != null) entity.setCausality(req.getCausality());
        if (req.getOutcome() != null) entity.setOutcome(req.getOutcome());
        if (req.getStartDate() != null) entity.setStartDate(req.getStartDate());
        if (req.getStopDate() != null) entity.setStopDate(req.getStopDate());
        if (req.getSummary() != null) entity.setSummary(req.getSummary());

        return AdverseEventResponse.fromEntity(adverseEventRepository.save(entity));
    }

    @Transactional
    public void deleteAdverseEvent(String aeId) {
        adverseEventRepository.findByAdverseEventId(aeId).ifPresent(adverseEventRepository::delete);
    }

    @Transactional(readOnly = true)
    public List<AdverseEventResponse> getStudyAdverseEvents(String studyId) {
        return adverseEventRepository.findByStudyId(studyId).stream()
                .map(AdverseEventResponse::fromEntity)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<AdverseEventResponse> getStudySiteAdverseEvents(String studyId, String siteId) {
        return adverseEventRepository.findByStudyIdAndSiteId(studyId, siteId).stream()
                .map(AdverseEventResponse::fromEntity)
                .toList();
    }

    @Transactional(readOnly = true)
    public AdverseEventResponse getAdverseEvent(String aeId) {
        return adverseEventRepository.findByAdverseEventId(aeId)
                .map(AdverseEventResponse::fromEntity)
                .orElseThrow(() -> new ResourceNotFoundException("Adverse event not found: " + aeId));
    }
}
