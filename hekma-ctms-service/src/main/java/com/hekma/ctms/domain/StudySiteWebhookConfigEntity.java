package com.hekma.ctms.domain;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Entity
@Table(name = "ctms_study_site_webhook_configs", uniqueConstraints = {
        @UniqueConstraint(name = "ctms_uq_webhook_study_site", columnNames = {"study_id", "site_id"})
})
public class StudySiteWebhookConfigEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "study_id", nullable = false, length = 100)
    private String studyId;

    @Column(name = "site_id", nullable = false, length = 100)
    private String siteId;

    @Column(name = "access_key", nullable = false, unique = true, length = 100)
    private String accessKey;

    @Column(name = "secret_key", nullable = false)
    private String secretKey;

    @Column(name = "created_by", length = 100)
    private String createdBy;

    @lombok.Builder.Default
    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();
}
