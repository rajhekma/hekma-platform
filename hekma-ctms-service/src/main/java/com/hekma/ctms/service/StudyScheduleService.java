package com.hekma.ctms.service;

import com.hekma.ctms.domain.*;
import com.hekma.ctms.exception.ResourceNotFoundException;
import com.hekma.ctms.repository.*;
import com.hekma.ctms.security.CtmsPrincipal;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class StudyScheduleService {

    private final StudyScheduleRepository scheduleRepository;
    private final StudyScheduleSegmentRepository segmentRepository;
    private final StudyScheduleEventRepository eventRepository;
    private final StudySchedulePatientProgressRepository progressRepository;

    @Transactional
    public StudyScheduleEntity createSchedule(String studyId, String scheduleName, CtmsPrincipal principal) {
        String scheduleId = "SCH-" + System.currentTimeMillis();
        StudyScheduleEntity schedule = StudyScheduleEntity.builder()
                .scheduleId(scheduleId)
                .studyId(studyId)
                .scheduleName(scheduleName != null ? scheduleName : "Default Schedule")
                .status("ACTIVE")
                .tenantId(principal != null ? principal.tenantId() : null)
                .tenantPath(principal != null ? principal.tenantPath() : null)
                .build();
        return scheduleRepository.save(schedule);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getScheduleDetails(String studyId, String scheduleId) {
        List<StudyScheduleEntity> schedules;
        if (scheduleId == null || scheduleId.isBlank() || "-1".equals(scheduleId)) {
            schedules = scheduleRepository.findByStudyId(studyId);
        } else {
            schedules = scheduleRepository.findByScheduleId(scheduleId).map(List::of).orElse(List.of());
        }

        if (schedules.isEmpty()) {
            return Map.of("studyId", studyId, "schedules", List.of());
        }

        String activeScheduleId = schedules.get(0).getScheduleId();
        List<StudyScheduleSegmentEntity> segments = segmentRepository.findByScheduleIdOrderBySegmentOrderAsc(activeScheduleId);
        List<StudyScheduleEventEntity> events = eventRepository.findByScheduleId(activeScheduleId);

        return Map.of(
                "studyId", studyId,
                "schedule", schedules.get(0),
                "segments", segments,
                "events", events
        );
    }

    @Transactional(readOnly = true)
    public List<StudySchedulePatientProgressEntity> getScheduleDetailsPatient(String studyId, String patientId, String siteId) {
        return progressRepository.findByScheduleIdAndPatientIdAndSiteId(studyId, patientId, siteId);
    }

    @Transactional
    public StudySchedulePatientProgressEntity updatePatientSchedule(String patSchedulePk, String startDate, String endDate) {
        StudySchedulePatientProgressEntity progress = progressRepository.findByPatSchedulePk(patSchedulePk)
                .orElseThrow(() -> new ResourceNotFoundException("Patient schedule progress not found: " + patSchedulePk));

        if (startDate != null) progress.setStartDate(startDate);
        if (endDate != null) progress.setEndDate(endDate);
        return progressRepository.save(progress);
    }

    @Transactional
    public StudySchedulePatientProgressEntity updatePatientScheduleCompletion(String patSchedulePk, String actualDate, String notes) {
        StudySchedulePatientProgressEntity progress = progressRepository.findByPatSchedulePk(patSchedulePk)
                .orElseThrow(() -> new ResourceNotFoundException("Patient schedule progress not found: " + patSchedulePk));

        if (actualDate != null) progress.setActualDate(actualDate);
        if (notes != null) progress.setNotes(notes);
        progress.setCompletedInd("Y");
        return progressRepository.save(progress);
    }
}
