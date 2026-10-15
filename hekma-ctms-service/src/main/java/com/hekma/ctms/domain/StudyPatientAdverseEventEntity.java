package com.hekma.ctms.domain;

import com.hekma.ctms.domain.common.BaseAuditEntity;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;
import org.hibernate.annotations.SQLRestriction;

import java.util.UUID;

@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@Entity
@Table(name = "ctms_study_patient_adverse_events")
@SQLRestriction("is_deleted = false")
public class StudyPatientAdverseEventEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "adverse_event_id", nullable = false, unique = true, length = 100)
    private String adverseEventId;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "site_id", nullable = false, length = 100)
    private String siteId;

    @Column(name = "patient_id", nullable = false, length = 100)
    private String patientId;

    @Column(name = "ae_term", nullable = false)
    private String aeTerm;

    @Column(name = "severity", length = 50)
    private String severity;

    @Column(name = "causality", length = 100)
    private String causality;

    @Column(name = "outcome", length = 100)
    private String outcome;

    @Column(name = "start_date", length = 100)
    private String startDate;

    @Column(name = "stop_date", length = 100)
    private String stopDate;

    @Column(name = "summary", columnDefinition = "TEXT")
    private String summary;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
