package com.hekma.notification.support.domain.repository;

import com.hekma.notification.support.domain.entity.SupportTicketEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface SupportTicketRepository extends JpaRepository<SupportTicketEntity, Long>,
        JpaSpecificationExecutor<SupportTicketEntity> {

    Optional<SupportTicketEntity> findByUuid(String uuid);

    Optional<SupportTicketEntity> findByTicketNumber(String ticketNumber);

    List<SupportTicketEntity> findByParticipantEmailIgnoreCaseOrderByCreatedTsDesc(String email);

    List<SupportTicketEntity> findByParticipantUserIdOrderByCreatedTsDesc(String userId);

    @Query("SELECT COUNT(t) FROM SupportTicketEntity t WHERE t.participantUserId = :userId AND t.status NOT IN ('RESOLVED', 'CLOSED')")
    long countOpenByParticipantUserId(@Param("userId") String userId);

    @Query("SELECT COUNT(t) FROM SupportTicketEntity t WHERE t.participantUserId = :userId AND t.status IN ('RESOLVED', 'CLOSED')")
    long countResolvedByParticipantUserId(@Param("userId") String userId);

    @Query("SELECT COUNT(t) FROM SupportTicketEntity t WHERE LOWER(t.participantEmail) = LOWER(:email) AND t.status NOT IN ('RESOLVED', 'CLOSED')")
    long countOpenByParticipantEmail(@Param("email") String email);

    @Query("SELECT COUNT(t) FROM SupportTicketEntity t WHERE LOWER(t.participantEmail) = LOWER(:email) AND t.status IN ('RESOLVED', 'CLOSED')")
    long countResolvedByParticipantEmail(@Param("email") String email);

    @Query("SELECT COUNT(t) FROM SupportTicketEntity t WHERE EXTRACT(YEAR FROM t.createdTs) = EXTRACT(YEAR FROM CURRENT_DATE)")
    long countTicketsThisYear();
}
