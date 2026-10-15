package com.hekma.ctms.repository;

import com.hekma.ctms.domain.AssessmentEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface AssessmentRepository extends JpaRepository<AssessmentEntity, Long> {

    Optional<AssessmentEntity> findByAssessmentName(String assessmentName);
}
