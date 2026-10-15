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
@Table(name = "ctms_study_events")
@SQLRestriction("is_deleted = false")
public class StudyEventEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_id", nullable = false, unique = true, length = 100)
    private String eventId;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "event_type", nullable = false, length = 50)
    private String eventType;

    @Column(name = "sub_type", length = 100)
    private String subType;

    @Column(name = "description", columnDefinition = "TEXT")
    private String description;

    @Column(name = "severity", length = 50)
    private String severity;

    @Column(name = "status", length = 50)
    private String status;

    @Column(name = "effective_date", length = 100)
    private String effectiveDate;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
