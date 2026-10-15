package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudySiteNoteEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface StudySiteNoteRepository extends JpaRepository<StudySiteNoteEntity, Long> {

    Optional<StudySiteNoteEntity> findByNoteId(String noteId);

    List<StudySiteNoteEntity> findByStudyIdAndSiteId(String studyId, String siteId);

    List<StudySiteNoteEntity> findByStudyIdAndSiteIdAndNoteType(String studyId, String siteId, String noteType);
}
