package com.hekma.ctms.dto;

import com.hekma.ctms.domain.StudyEntity;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class StudyResponse {
    private Long id;
    private String studyId;
    private String studyNumber;
    private String protocolNumber;
    private Long parentAccountId;
    private String studyTitle;
    private String nameOfImp;
    private String devPhase;
    private String status;
    private String primaryEndPoint;
    private String secondaryEndPoint;
    private String expEndPoint;
    private LocalDate startDate;
    private LocalDate endDate;
    private String studyDuration;
    private String stoppingCriteria;
    private String numberOfSitesPlanned;
    private String numberOfSubPlanned;
    private String route;
    private String regiman;
    private String dosage;
    private String statMethod;
    private String interimAnalysis;
    private String studyFlow;
    private String studyStatus;
    private String studyType;
    private String studyPhase;
    private String sponsorType;
    private String indication;
    private String therapeuticArea;
    private UUID tenantId;
    private String tenantPath;
    private Instant createdAt;
    private Instant updatedAt;

    public static StudyResponse fromEntity(StudyEntity entity) {
        if (entity == null) return null;
        return StudyResponse.builder()
                .id(entity.getId())
                .studyId(entity.getStudyId())
                .studyNumber(entity.getStudyNumber())
                .protocolNumber(entity.getProtocolNumber())
                .parentAccountId(entity.getParentAccountId())
                .studyTitle(entity.getStudyTitle())
                .nameOfImp(entity.getNameOfImp())
                .devPhase(entity.getDevPhase())
                .status(entity.getStatus())
                .primaryEndPoint(entity.getPrimaryEndPoint())
                .secondaryEndPoint(entity.getSecondaryEndPoint())
                .expEndPoint(entity.getExpEndPoint())
                .startDate(entity.getStartDate())
                .endDate(entity.getEndDate())
                .studyDuration(entity.getStudyDuration())
                .stoppingCriteria(entity.getStoppingCriteria())
                .numberOfSitesPlanned(entity.getNumberOfSitesPlanned())
                .numberOfSubPlanned(entity.getNumberOfSubPlanned())
                .route(entity.getRoute())
                .regiman(entity.getRegiman())
                .dosage(entity.getDosage())
                .statMethod(entity.getStatMethod())
                .interimAnalysis(entity.getInterimAnalysis())
                .studyFlow(entity.getStudyFlow())
                .studyStatus(entity.getStudyStatus())
                .studyType(entity.getStudyType())
                .studyPhase(entity.getStudyPhase())
                .sponsorType(entity.getSponsorType())
                .indication(entity.getIndication())
                .therapeuticArea(entity.getTherapeuticArea())
                .tenantId(entity.getTenantId())
                .tenantPath(entity.getTenantPath())
                .createdAt(entity.getCreatedAt())
                .updatedAt(entity.getUpdatedAt())
                .build();
    }
}
