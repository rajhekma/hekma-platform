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
@Table(name = "ctms_study_sites", uniqueConstraints = {
        @UniqueConstraint(name = "ctms_uq_study_site", columnNames = {"study_id", "site_id"})
})
@SQLRestriction("is_deleted = false")
public class StudySiteEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "site_id", nullable = false, length = 100)
    private String siteId;

    @Column(name = "site_name")
    private String siteName;

    @Column(name = "site_user_id", length = 100)
    private String siteUserId;

    @Column(name = "status", length = 50)
    private String status;

    @Column(name = "onboard_status", length = 50)
    private String onboardStatus;

    @Column(name = "limitization", length = 100)
    private String limitization;

    @Column(name = "primary_contact")
    private String primaryContact;

    @Column(name = "role", length = 100)
    private String role;

    @Column(name = "imp_received", length = 50)
    private String impReceived;

    @Column(name = "placeholder")
    private String placeholder;

    @Column(name = "tenant_id")
    private UUID tenantId;

    @Column(name = "tenant_path")
    private String tenantPath;
}
