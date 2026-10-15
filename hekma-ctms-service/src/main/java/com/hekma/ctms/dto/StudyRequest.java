package com.hekma.ctms.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class StudyRequest {
    private String studyNumber;
    private String protocolNumber;
    private Long parentAccountId;
    @NotBlank(message = "studyTitle is required")
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
}
