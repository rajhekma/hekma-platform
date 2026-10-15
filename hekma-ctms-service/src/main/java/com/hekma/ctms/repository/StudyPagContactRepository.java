package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyPagContactEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface StudyPagContactRepository extends JpaRepository<StudyPagContactEntity, Long> {

    List<StudyPagContactEntity> findByStudyIdAndPagId(String studyId, String pagId);
}
