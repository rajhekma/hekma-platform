package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyPatientAdverseEventEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudyPatientAdverseEventRepository extends JpaRepository<StudyPatientAdverseEventEntity, Long> {

    Optional<StudyPatientAdverseEventEntity> findByAdverseEventId(String adverseEventId);

    List<StudyPatientAdverseEventEntity> findByStudyId(String studyId);

    List<StudyPatientAdverseEventEntity> findByStudyIdAndSiteId(String studyId, String siteId);

    List<StudyPatientAdverseEventEntity> findByStudyIdAndSiteIdAndPatientId(String studyId, String siteId, String patientId);
}
