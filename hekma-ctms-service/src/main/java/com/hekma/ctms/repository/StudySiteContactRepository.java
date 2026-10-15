package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudySiteContactEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudySiteContactRepository extends JpaRepository<StudySiteContactEntity, Long> {

    List<StudySiteContactEntity> findByStudyIdAndSiteId(String studyId, String siteId);

    Optional<StudySiteContactEntity> findByStudyIdAndSiteIdAndContactId(String studyId, String siteId, String contactId);
}
