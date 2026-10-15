package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyArmEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudyArmRepository extends JpaRepository<StudyArmEntity, Long> {

    List<StudyArmEntity> findByStudyId(String studyId);

    Optional<StudyArmEntity> findByArmNum(String armNum);
}
