package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportTicketNotificationHistoryEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SupportTicketNotificationHistoryRepository extends JpaRepository<SupportTicketNotificationHistoryEntity, Long> {

    List<SupportTicketNotificationHistoryEntity> findByTicketIdOrderByCreatedTsAsc(Long ticketId);
}
