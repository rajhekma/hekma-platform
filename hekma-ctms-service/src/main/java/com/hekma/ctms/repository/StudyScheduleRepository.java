package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyScheduleEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudyScheduleRepository extends JpaRepository<StudyScheduleEntity, Long> {

    Optional<StudyScheduleEntity> findByScheduleId(String scheduleId);

    List<StudyScheduleEntity> findByStudyId(String studyId);
}
