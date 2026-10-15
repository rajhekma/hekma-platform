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
@Table(name = "ctms_study_contacts")
@SQLRestriction("is_deleted = false")
public class StudyContactEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "contact_id", nullable = false, length = 100)
    private String contactId;

    @Column(name = "role", length = 100)
    private String role;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
