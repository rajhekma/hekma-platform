package com.hekma.ctms.repository;

import com.hekma.ctms.domain.StudyArmDetailEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface StudyArmDetailRepository extends JpaRepository<StudyArmDetailEntity, Long> {

    List<StudyArmDetailEntity> findByArmNum(String armNum);
}
