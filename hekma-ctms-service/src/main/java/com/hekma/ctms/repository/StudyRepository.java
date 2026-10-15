package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudyRepository extends JpaRepository<StudyEntity, Long>, JpaSpecificationExecutor<StudyEntity> {

    Optional<StudyEntity> findByStudyId(String studyId);

    Optional<StudyEntity> findByStudyNumber(String studyNumber);

    List<StudyEntity> findByParentAccountId(Long parentAccountId);

    List<StudyEntity> findByTenantPathStartingWith(String tenantPathPrefix);
}
