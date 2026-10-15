package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportTicketStatusHistoryEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SupportTicketStatusHistoryRepository extends JpaRepository<SupportTicketStatusHistoryEntity, Long> {

    List<SupportTicketStatusHistoryEntity> findByTicketIdOrderByCreatedTsAsc(Long ticketId);
}
