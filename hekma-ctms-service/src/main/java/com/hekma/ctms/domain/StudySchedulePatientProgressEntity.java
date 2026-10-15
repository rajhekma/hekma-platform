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
@Table(name = "ctms_study_schedule_patient_progress")
@SQLRestriction("is_deleted = false")
public class StudySchedulePatientProgressEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "pat_schedule_pk", nullable = false, unique = true, length = 100)
    private String patSchedulePk;

    @Column(name = "schedule_id", nullable = false, length = 100)
    private String scheduleId;

    @Column(name = "site_id", nullable = false, length = 100)
    private String siteId;

    @Column(name = "patient_id", nullable = false, length = 100)
    private String patientId;

    @Column(name = "event_id", length = 100)
    private String eventId;

    @Column(name = "event_name")
    private String eventName;

    @Column(name = "start_date", length = 100)
    private String startDate;

    @Column(name = "end_date", length = 100)
    private String endDate;

    @Column(name = "actual_date", length = 100)
    private String actualDate;

    @Column(name = "completed_ind", length = 10)
    private String completedInd;

    @Column(name = "notes", columnDefinition = "TEXT")
    private String notes;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
