package com.hekma.ctms.dto;

import com.hekma.ctms.domain.StudySiteQueryEntity;
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
public class StudyQueryResponse {
    private Long id;
    private String queryId;
    private String queryNum;
    private String studyId;
    private String studyName;
    private String siteId;
    private String queryTitle;
    private String queryDescription;
    private String category;
    private String severity;
    private String status;
    private String assignedTo;
    private String assignedToName;
    private String sponsorReference1;
    private String sponsorReference2;
    private String siteReference1;
    private String siteReference2;
    private String createdByName;
    private String queryResponse;
    private UUID tenantId;
    private String tenantPath;
    private Instant createdAt;

    public static StudyQueryResponse fromEntity(StudySiteQueryEntity entity) {
        if (entity == null) return null;
        return StudyQueryResponse.builder()
                .id(entity.getId())
                .queryId(entity.getQueryId())
                .queryNum(entity.getQueryNum())
                .studyId(entity.getStudyId())
                .studyName(entity.getStudyName())
                .siteId(entity.getSiteId())
                .queryTitle(entity.getQueryTitle())
                .queryDescription(entity.getQueryDescription())
                .category(entity.getCategory())
                .severity(entity.getSeverity())
                .status(entity.getStatus())
                .assignedTo(entity.getAssignedTo())
                .assignedToName(entity.getAssignedToName())
                .sponsorReference1(entity.getSponsorReference1())
                .sponsorReference2(entity.getSponsorReference2())
                .siteReference1(entity.getSiteReference1())
                .siteReference2(entity.getSiteReference2())
                .createdByName(entity.getCreatedByName())
                .queryResponse(entity.getQueryResponse())
                .tenantId(entity.getTenantId())
                .tenantPath(entity.getTenantPath())
                .createdAt(entity.getCreatedAt())
                .build();
    }
}
