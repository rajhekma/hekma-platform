package com.hekma.appointment.repository;

import com.hekma.appointment.domain.AppointmentEntity;
import com.hekma.appointment.domain.AppointmentStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

@Repository
public interface AppointmentRepository extends JpaRepository<AppointmentEntity, UUID>, JpaSpecificationExecutor<AppointmentEntity> {

    @Query("""
        SELECT COUNT(a) FROM AppointmentEntity a
        WHERE a.status NOT IN ('CLOSED', 'CANCELLED')
          AND (:excludeId IS NULL OR a.id != :excludeId)
          AND ((a.fromKey = :userKey AND a.fromType = :userType) OR (a.toKey = :userKey AND a.toType = :userType))
          AND a.startDateTime < :endDateTime
          AND a.endDateTime > :startDateTime
    """)
    long countConflictingAppointments(
            @Param("userKey") String userKey,
            @Param("userType") String userType,
            @Param("startDateTime") Instant startDateTime,
            @Param("endDateTime") Instant endDateTime,
            @Param("excludeId") UUID excludeId
    );

    List<AppointmentEntity> findByStatusInAndStartDateTimeBetweenAndReminder1hSentFalse(
            Collection<AppointmentStatus> statuses, Instant start, Instant end
    );

    List<AppointmentEntity> findByStatusInAndStartDateTimeBetweenAndReminder1dSentFalse(
            Collection<AppointmentStatus> statuses, Instant start, Instant end
    );

    List<AppointmentEntity> findByStatusInAndStartDateTimeBetweenAndReminder7dSentFalse(
            Collection<AppointmentStatus> statuses, Instant start, Instant end
    );
}
