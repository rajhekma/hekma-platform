package com.hekma.ctms.repository;

import com.hekma.ctms.domain.CourseResourceEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface CourseResourceRepository extends JpaRepository<CourseResourceEntity, Long> {

    Optional<CourseResourceEntity> findByResourceId(String resourceId);

    List<CourseResourceEntity> findByStudyId(String studyId);

    List<CourseResourceEntity> findByStudyIdAndCrsResInd(String studyId, String crsResInd);
}
