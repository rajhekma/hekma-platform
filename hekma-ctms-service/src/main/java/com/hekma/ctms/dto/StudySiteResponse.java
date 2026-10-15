package com.hekma.ctms.dto;

import com.hekma.ctms.domain.StudySiteEntity;
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
public class StudySiteResponse {
    private Long id;
    private String studyId;
    private String siteId;
    private String siteName;
    private String siteUserId;
    private String status;
    private String onboardStatus;
    private String limitization;
    private String primaryContact;
    private String role;
    private String impReceived;
    private String placeholder;
    private UUID tenantId;
    private String tenantPath;
    private Instant createdAt;

    public static StudySiteResponse fromEntity(StudySiteEntity entity) {
        if (entity == null) return null;
        return StudySiteResponse.builder()
                .id(entity.getId())
                .studyId(entity.getStudyId())
                .siteId(entity.getSiteId())
                .siteName(entity.getSiteName())
                .siteUserId(entity.getSiteUserId())
                .status(entity.getStatus())
                .onboardStatus(entity.getOnboardStatus())
                .limitization(entity.getLimitization())
                .primaryContact(entity.getPrimaryContact())
                .role(entity.getRole())
                .impReceived(entity.getImpReceived())
                .placeholder(entity.getPlaceholder())
                .tenantId(entity.getTenantId())
                .tenantPath(entity.getTenantPath())
                .createdAt(entity.getCreatedAt())
                .build();
    }
}
