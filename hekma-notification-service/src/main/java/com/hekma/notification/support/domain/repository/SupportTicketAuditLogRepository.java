package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportTicketAuditLogEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SupportTicketAuditLogRepository extends JpaRepository<SupportTicketAuditLogEntity, Long> {

    List<SupportTicketAuditLogEntity> findByTicketIdOrderByCreatedTsAsc(Long ticketId);
}
