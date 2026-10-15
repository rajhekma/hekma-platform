package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportTicketAttachmentEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SupportTicketAttachmentRepository extends JpaRepository<SupportTicketAttachmentEntity, Long> {

    List<SupportTicketAttachmentEntity> findByTicketIdOrderByCreatedTsAsc(Long ticketId);

    long countByTicketIdAndIsDeletedFalse(Long ticketId);
}
