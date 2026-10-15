package com.hekma.ctms.service;

import com.hekma.ctms.domain.*;
import com.hekma.ctms.dto.*;
import com.hekma.ctms.repository.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class CmtsWebhookService {

    private final StudySiteWebhookConfigRepository webhookConfigRepository;
    private final StudyService studyService;
    private final StudySiteService studySiteService;
    private final AdverseEventService adverseEventService;
    private final StudyScheduleService studyScheduleService;
    private final StudySitePatientRepository studySitePatientRepository;
    private final CourseResourceRepository courseResourceRepository;

    @Transactional
    public Map<String, String> generateKeys(String studyId, String siteId, String createdBy) {
        Optional<StudySiteWebhookConfigEntity> existing = webhookConfigRepository.findByStudyIdAndSiteId(studyId, siteId);
        if (existing.isPresent()) {
            StudySiteWebhookConfigEntity config = existing.get();
            return Map.of(
                    "accessKey", config.getAccessKey(),
                    "secretKey", config.getSecretKey()
            );
        }

        String accessKey = UUID.randomUUID().toString().replace("-", "");
        String secretKey = UUID.randomUUID().toString().replace("-", "");

        StudySiteWebhookConfigEntity config = StudySiteWebhookConfigEntity.builder()
                .studyId(studyId)
                .siteId(siteId)
                .accessKey(accessKey)
                .secretKey(secretKey)
                .createdBy(createdBy != null ? createdBy : "admin")
                .createdAt(Instant.now())
                .build();

        webhookConfigRepository.save(config);
        log.info("Generated EDC webhook keys for studyId={}, siteId={}", studyId, siteId);
        return Map.of(
                "accessKey", accessKey,
                "secretKey", secretKey
        );
    }

    @Transactional(readOnly = true)
    public StudySiteWebhookConfigEntity getWebhookConfig(String accessKey, String secretKey) {
        return webhookConfigRepository.findByAccessKeyAndSecretKey(accessKey, secretKey).orElse(null);
    }

    @Transactional
    public ApiResponse<String> processWebhook(String accessKey, String secretKey, CmtsWebhookPayload payload) {
        StudySiteWebhookConfigEntity config = getWebhookConfig(accessKey, secretKey);
        if (config == null) {
            return ApiResponse.error(401, "Invalid access key or secret key");
        }

        if (!config.getStudyId().equals(payload.getStudyId()) || !config.getSiteId().equals(payload.getSiteId())) {
            return ApiResponse.error(403, "Access key and secret key do not match the target studyId and siteId");
        }

        if (payload.getResourceType() == null) {
            return ApiResponse.error(400, "Missing resourceType");
        }

        String type = payload.getResourceType().toUpperCase();
        try {
            switch (type) {
                case "ADVERSE_EVENTS" -> {
                    Map<String, Object> data = payload.getData() != null ? payload.getData() : Map.of();
                    String adverseEventId = payload.getAdverseEventId();
                    AdverseEventRequest req = AdverseEventRequest.builder()
                            .adverseEventId(adverseEventId)
                            .studyId(payload.getStudyId())
                            .siteId(payload.getSiteId())
                            .patientId(payload.getPatientId() != null ? payload.getPatientId() : (String) data.get("patientId"))
                            .aeTerm((String) data.getOrDefault("aeTerm", "Unknown Event"))
                            .severity((String) data.get("severity"))
                            .causality((String) data.get("causality"))
                            .outcome((String) data.get("outcome"))
                            .startDate((String) data.get("startDate"))
                            .stopDate((String) data.get("stopDate"))
                            .summary((String) data.get("summary"))
                            .build();

                    AdverseEventResponse res = (adverseEventId != null && !adverseEventId.isBlank())
                            ? adverseEventService.updateAdverseEvent(adverseEventId, req, null)
                            : adverseEventService.createAdverseEvent(req, null);

                    return ApiResponse.ok("Adverse event processed successfully", res.getAdverseEventId());
                }
                case "PATIENT_SCHEDULED_CHANGES" -> {
                    Map<String, Object> data = payload.getData() != null ? payload.getData() : Map.of();
                    String patSchedulePk = (String) data.get("patSchedulePk");
                    if (patSchedulePk != null) {
                        studyScheduleService.updatePatientSchedule(
                                patSchedulePk,
                                (String) data.get("startDate"),
                                (String) data.get("endDate")
                        );
                    }
                    return ApiResponse.ok("Patient schedule updated successfully", "OK");
                }
                default -> {
                    return ApiResponse.error(400, "Unsupported resource type: " + type);
                }
            }
        } catch (Exception e) {
            log.error("Failed to process webhook for resourceType {}: {}", type, e.getMessage());
            return ApiResponse.error(500, "Webhook processing error: " + e.getMessage());
        }
    }

    @Transactional(readOnly = true)
    public ApiResponse<Object> loadData(String accessKey, String secretKey, String resourceType,
                                        String studyId, String siteId, String scheduleId, String eventType,
                                        String patientId, String armNum, String noteId, String noteType,
                                        String queryId, String statuses, String assignedTo) {
        StudySiteWebhookConfigEntity config = getWebhookConfig(accessKey, secretKey);
        if (config == null) {
            return ApiResponse.error(401, "Invalid access key or secret key");
        }

        if (studyId != null && !studyId.isBlank() && !config.getStudyId().equals(studyId)) {
            return ApiResponse.error(403, "Access key does not match studyId");
        }
        if (siteId != null && !siteId.isBlank() && !config.getSiteId().equals(siteId)) {
            return ApiResponse.error(403, "Access key does not match siteId");
        }

        String targetStudyId = config.getStudyId();
        String targetSiteId = config.getSiteId();
        String type = resourceType != null ? resourceType.toUpperCase() : "";

        Object data = switch (type) {
            case "STUDY" -> studyService.getStudy(targetStudyId, null);
            case "STUDY_CONTACT" -> studyService.getStudyContacts(targetStudyId);
            case "STUDY_PAG" -> studySiteService.getStudyPags(targetStudyId);
            case "STUDY_ARM" -> (armNum != null && !armNum.isBlank())
                    ? studyService.getStudyArmDetails(armNum)
                    : studyService.getStudyArms(targetStudyId);
            case "STUDY_SCHEDULE" -> studyScheduleService.getScheduleDetails(targetStudyId, scheduleId);
            case "STUDY_INCLUSION_CRITERIA" -> studyService.getStudyEvents(targetStudyId, "I");
            case "STUDY_EXCLUSION_CRITERIA" -> studyService.getStudyEvents(targetStudyId, "E");
            case "STUDY_RBM" -> studyService.getStudyEvents(targetStudyId, "R");
            case "STUDY_EVENT" -> studyService.getStudyEvents(targetStudyId, eventType);
            case "STUDY_COURSE_RESOURCE" -> courseResourceRepository.findByStudyId(targetStudyId);
            case "STUDY_SITE" -> studySiteService.getStudySite(targetStudyId, targetSiteId);
            case "STUDY_SITE_CONTACT" -> studySiteService.getStudySiteContacts(targetStudyId, targetSiteId);
            case "STUDY_SITE_PATIENT" -> studySitePatientRepository.findByStudyIdAndSiteId(targetStudyId, targetSiteId);
            case "STUDY_SITE_ADVERSE_EVENTS" -> adverseEventService.getStudySiteAdverseEvents(targetStudyId, targetSiteId);
            case "STUDY_SITE_QUERY" -> studySiteService.getStudySiteQueries(targetStudyId, targetSiteId);
            case "STUDY_SITE_NOTE" -> studySiteService.getStudySiteNotes(targetStudyId, targetSiteId);
            case "PATIENT_SCHEDULE" -> studyScheduleService.getScheduleDetailsPatient(targetStudyId, patientId, targetSiteId);
            default -> null;
        };

        if (data == null) {
            return ApiResponse.error(400, "Unsupported or unhandled resource type: " + type);
        }
        return ApiResponse.ok("Data fetched successfully for resource type: " + type, data);
    }
}
