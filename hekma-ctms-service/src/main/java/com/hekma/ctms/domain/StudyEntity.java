package com.hekma.ctms.domain;

import com.hekma.ctms.domain.common.BaseAuditEntity;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;
import org.hibernate.annotations.SQLRestriction;

import java.time.LocalDate;
import java.util.UUID;

@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@Entity
@Table(name = "ctms_studies")
@SQLRestriction("is_deleted = false")
public class StudyEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "study_id", nullable = false, unique = true, length = 100)
    private String studyId;

    @Column(name = "study_number", nullable = false, unique = true, length = 100)
    private String studyNumber;

    @Column(name = "protocol_number", length = 100)
    private String protocolNumber;

    @Column(name = "parent_account_id")
    private Long parentAccountId;

    @Column(name = "study_title", nullable = false, columnDefinition = "TEXT")
    private String studyTitle;

    @Column(name = "name_of_imp")
    private String nameOfImp;

    @Column(name = "dev_phase", length = 100)
    private String devPhase;

    @lombok.Builder.Default
    @Column(name = "status", nullable = false, length = 50)
    private String status = "DRAFT";

    @Column(name = "primary_end_point", columnDefinition = "TEXT")
    private String primaryEndPoint;

    @Column(name = "secondary_end_point", columnDefinition = "TEXT")
    private String secondaryEndPoint;

    @Column(name = "exp_end_point", columnDefinition = "TEXT")
    private String expEndPoint;

    @Column(name = "start_date")
    private LocalDate startDate;

    @Column(name = "end_date")
    private LocalDate endDate;

    @Column(name = "study_duration", length = 100)
    private String studyDuration;

    @Column(name = "stopping_criteria", columnDefinition = "TEXT")
    private String stoppingCriteria;

    @Column(name = "number_of_sites_planned", length = 50)
    private String numberOfSitesPlanned;

    @Column(name = "number_of_sub_planned", length = 50)
    private String numberOfSubPlanned;

    @Column(name = "route", length = 100)
    private String route;

    @Column(name = "regiman")
    private String regiman;

    @Column(name = "dosage")
    private String dosage;

    @Column(name = "stat_method")
    private String statMethod;

    @Column(name = "interim_analysis")
    private String interimAnalysis;

    @Column(name = "study_flow", columnDefinition = "TEXT")
    private String studyFlow;

    @Column(name = "study_status", length = 50)
    private String studyStatus;

    @Column(name = "study_type", length = 100)
    private String studyType;

    @Column(name = "study_phase", length = 100)
    private String studyPhase;

    @Column(name = "sponsor_type", length = 100)
    private String sponsorType;

    @Column(name = "indication")
    private String indication;

    @Column(name = "therapeutic_area")
    private String therapeuticArea;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
