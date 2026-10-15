package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudySiteWebhookConfigEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface StudySiteWebhookConfigRepository extends JpaRepository<StudySiteWebhookConfigEntity, Long> {

    Optional<StudySiteWebhookConfigEntity> findByAccessKeyAndSecretKey(String accessKey, String secretKey);

    Optional<StudySiteWebhookConfigEntity> findByStudyIdAndSiteId(String studyId, String siteId);
}
