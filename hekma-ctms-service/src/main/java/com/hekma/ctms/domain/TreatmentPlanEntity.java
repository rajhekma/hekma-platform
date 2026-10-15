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
@Table(name = "ctms_treatment_plans")
@SQLRestriction("is_deleted = false")
public class TreatmentPlanEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "plan_id", nullable = false, unique = true, length = 100)
    private String planId;

    @Column(name = "site_id", nullable = false, length = 100)
    private String siteId;

    @Column(name = "plan_name", nullable = false)
    private String planName;

    @Column(name = "plan_description", columnDefinition = "TEXT")
    private String planDescription;

    @Column(name = "classification", length = 100)
    private String classification;

    @lombok.Builder.Default
    @Column(name = "status", length = 50)
    private String status = "ACTIVE";

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
