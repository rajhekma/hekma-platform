package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyContactEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudyContactRepository extends JpaRepository<StudyContactEntity, Long> {

    List<StudyContactEntity> findByStudyId(String studyId);

    Optional<StudyContactEntity> findByStudyIdAndContactId(String studyId, String contactId);
}
