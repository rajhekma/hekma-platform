package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportTicketCommentEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SupportTicketCommentRepository extends JpaRepository<SupportTicketCommentEntity, Long> {

    List<SupportTicketCommentEntity> findByTicketIdOrderByCreatedTsAsc(Long ticketId);

    List<SupportTicketCommentEntity> findByTicketIdAndIsInternalFalseOrderByCreatedTsAsc(Long ticketId);
}
