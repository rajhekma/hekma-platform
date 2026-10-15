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
@Table(name = "ctms_study_site_queries")
@SQLRestriction("is_deleted = false")
public class StudySiteQueryEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "query_id", nullable = false, unique = true, length = 100)
    private String queryId;

    @Column(name = "query_num", length = 100)
    private String queryNum;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "study_name")
    private String studyName;

    @Column(name = "site_id", nullable = false, length = 100)
    private String siteId;

    @Column(name = "query_title", nullable = false)
    private String queryTitle;

    @Column(name = "query_description", columnDefinition = "TEXT")
    private String queryDescription;

    @Column(name = "category", length = 100)
    private String category;

    @Column(name = "severity", length = 50)
    private String severity;

    @lombok.Builder.Default
    @Column(name = "status", nullable = false, length = 50)
    private String status = "OPEN";

    @Column(name = "assigned_to", length = 100)
    private String assignedTo;

    @Column(name = "assigned_to_name")
    private String assignedToName;

    @Column(name = "sponsor_reference1")
    private String sponsorReference1;

    @Column(name = "sponsor_reference2")
    private String sponsorReference2;

    @Column(name = "site_reference1")
    private String siteReference1;

    @Column(name = "site_reference2")
    private String siteReference2;

    @Column(name = "created_by_name")
    private String createdByName;

    @Column(name = "query_response", columnDefinition = "TEXT")
    private String queryResponse;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
