package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportSlaTrackingEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface SupportSlaTrackingRepository extends JpaRepository<SupportSlaTrackingEntity, Long> {

    Optional<SupportSlaTrackingEntity> findByTicketId(Long ticketId);
}
