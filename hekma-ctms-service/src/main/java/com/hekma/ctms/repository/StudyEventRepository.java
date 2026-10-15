package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyEventEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudyEventRepository extends JpaRepository<StudyEventEntity, Long> {

    List<StudyEventEntity> findByStudyId(String studyId);

    List<StudyEventEntity> findByStudyIdAndEventType(String studyId, String eventType);

    Optional<StudyEventEntity> findByEventId(String eventId);
}
