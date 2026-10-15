package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyScheduleEventEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface StudyScheduleEventRepository extends JpaRepository<StudyScheduleEventEntity, Long> {

    List<StudyScheduleEventEntity> findByScheduleId(String scheduleId);
}
