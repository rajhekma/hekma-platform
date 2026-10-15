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
@Table(name = "ctms_course_resources")
@SQLRestriction("is_deleted = false")
public class CourseResourceEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "resource_id", nullable = false, unique = true, length = 100)
    private String resourceId;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "crs_res_ind", length = 50)
    private String crsResInd;

    @Column(name = "summary", columnDefinition = "TEXT")
    private String summary;

    @Column(name = "type", length = 100)
    private String type;

    @Column(name = "category", length = 100)
    private String category;

    @Column(name = "language", length = 50)
    private String language;

    @Column(name = "version_str", length = 50)
    private String versionStr;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
