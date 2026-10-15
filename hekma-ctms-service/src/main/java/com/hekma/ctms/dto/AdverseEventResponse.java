package com.hekma.ctms.dto;

import com.hekma.ctms.domain.StudyPatientAdverseEventEntity;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdverseEventResponse {
    private Long id;
    private String adverseEventId;
    private String studyId;
    private String siteId;
    private String patientId;
    private String aeTerm;
    private String severity;
    private String causality;
    private String outcome;
    private String startDate;
    private String stopDate;
    private String summary;
    private UUID tenantId;
    private String tenantPath;
    private Instant createdAt;

    public static AdverseEventResponse fromEntity(StudyPatientAdverseEventEntity entity) {
        if (entity == null) return null;
        return AdverseEventResponse.builder()
                .id(entity.getId())
                .adverseEventId(entity.getAdverseEventId())
                .studyId(entity.getStudyId())
                .siteId(entity.getSiteId())
                .patientId(entity.getPatientId())
                .aeTerm(entity.getAeTerm())
                .severity(entity.getSeverity())
                .causality(entity.getCausality())
                .outcome(entity.getOutcome())
                .startDate(entity.getStartDate())
                .stopDate(entity.getStopDate())
                .summary(entity.getSummary())
                .tenantId(entity.getTenantId())
                .tenantPath(entity.getTenantPath())
                .createdAt(entity.getCreatedAt())
                .build();
    }
}
