package com.hekma.ctms.repository;

import com.hekma.ctms.domain.TreatmentPlanEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface TreatmentPlanRepository extends JpaRepository<TreatmentPlanEntity, Long> {

    List<TreatmentPlanEntity> findBySiteId(String siteId);

    Optional<TreatmentPlanEntity> findByPlanId(String planId);
}
