package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyScheduleSegmentEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface StudyScheduleSegmentRepository extends JpaRepository<StudyScheduleSegmentEntity, Long> {

    List<StudyScheduleSegmentEntity> findByScheduleIdOrderBySegmentOrderAsc(String scheduleId);
}
