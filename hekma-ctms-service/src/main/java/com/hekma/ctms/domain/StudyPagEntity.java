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
@Table(name = "ctms_study_pags", uniqueConstraints = {
        @UniqueConstraint(name = "ctms_uq_study_pag", columnNames = {"study_id", "pag_id"})
})
@SQLRestriction("is_deleted = false")
public class StudyPagEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "pag_id", nullable = false, length = 100)
    private String pagId;

    @Column(name = "status", length = 50)
    private String status;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
