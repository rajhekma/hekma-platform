package com.hekma.ctms.repository;

import com.hekma.ctms.domain.SupportDetailEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SupportDetailRepository extends JpaRepository<SupportDetailEntity, Long> {

    List<SupportDetailEntity> findByBuAreaAndBuId(String buArea, String buId);

    List<SupportDetailEntity> findByBuAreaAndBuIdAndStatus(String buArea, String buId, String status);
}
