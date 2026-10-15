package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyPagEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudyPagRepository extends JpaRepository<StudyPagEntity, Long> {

    List<StudyPagEntity> findByStudyId(String studyId);

    Optional<StudyPagEntity> findByStudyIdAndPagId(String studyId, String pagId);
}
