package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudySchedulePatientProgressEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudySchedulePatientProgressRepository extends JpaRepository<StudySchedulePatientProgressEntity, Long> {

    Optional<StudySchedulePatientProgressEntity> findByPatSchedulePk(String patSchedulePk);

    List<StudySchedulePatientProgressEntity> findByScheduleIdAndPatientIdAndSiteId(String scheduleId, String patientId, String siteId);

    List<StudySchedulePatientProgressEntity> findByScheduleId(String scheduleId);
}
