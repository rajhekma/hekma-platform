package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudySiteEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudySiteRepository extends JpaRepository<StudySiteEntity, Long> {

    List<StudySiteEntity> findByStudyId(String studyId);

    List<StudySiteEntity> findBySiteId(String siteId);

    Optional<StudySiteEntity> findByStudyIdAndSiteId(String studyId, String siteId);
}
