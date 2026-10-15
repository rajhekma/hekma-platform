package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudySiteQueryEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudySiteQueryRepository extends JpaRepository<StudySiteQueryEntity, Long>, JpaSpecificationExecutor<StudySiteQueryEntity> {

    Optional<StudySiteQueryEntity> findByQueryId(String queryId);

    List<StudySiteQueryEntity> findByStudyIdAndSiteId(String studyId, String siteId);

    List<StudySiteQueryEntity> findByStudyId(String studyId);
}
