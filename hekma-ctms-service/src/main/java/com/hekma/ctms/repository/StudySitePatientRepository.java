package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudySitePatientEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudySitePatientRepository extends JpaRepository<StudySitePatientEntity, Long>, JpaSpecificationExecutor<StudySitePatientEntity> {

    List<StudySitePatientEntity> findByStudyIdAndSiteId(String studyId, String siteId);

    List<StudySitePatientEntity> findByStudyIdAndSiteIdAndOnboardStatus(String studyId, String siteId, String onboardStatus);

    Optional<StudySitePatientEntity> findByStudyIdAndSiteIdAndPatientId(String studyId, String siteId, String patientId);

    List<StudySitePatientEntity> findByPatientId(String patientId);
}
