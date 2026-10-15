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
@Table(name = "ctms_study_site_patients", uniqueConstraints = {
        @UniqueConstraint(name = "ctms_uq_study_site_patient", columnNames = {"study_id", "site_id", "patient_id"})
})
@SQLRestriction("is_deleted = false")
public class StudySitePatientEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "site_id", nullable = false, length = 100)
    private String siteId;

    @Column(name = "patient_id", nullable = false, length = 100)
    private String patientId;

    @Column(name = "subject_id", length = 100)
    private String subjectId;

    @Column(name = "alternate_id", length = 100)
    private String alternateId;

    @Column(name = "subject_status", length = 50)
    private String subjectStatus;

    @Column(name = "onboard_status", length = 50)
    private String onboardStatus;

    @Column(name = "arm_num")
    private Integer armNum;

    @Column(name = "note", columnDefinition = "TEXT")
    private String note;

    @Column(name = "first_name", length = 100)
    private String firstName;

    @Column(name = "last_name", length = 100)
    private String lastName;

    @Column(name = "email")
    private String email;

    @Column(name = "phone", length = 50)
    private String phone;

    @Column(name = "gender", length = 50)
    private String gender;

    @Column(name = "dob", length = 50)
    private String dob;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
