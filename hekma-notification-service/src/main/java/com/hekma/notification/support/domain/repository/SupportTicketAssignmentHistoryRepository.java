package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportTicketAssignmentHistoryEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SupportTicketAssignmentHistoryRepository extends JpaRepository<SupportTicketAssignmentHistoryEntity, Long> {

    List<SupportTicketAssignmentHistoryEntity> findByTicketIdOrderByCreatedTsAsc(Long ticketId);
}
