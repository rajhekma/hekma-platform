package com.hekma.appointment.service;

import com.hekma.appointment.dto.ConflictCheckRequest;
import com.hekma.appointment.dto.ConflictCheckResponse;
import com.hekma.appointment.exception.ConflictException;
import com.hekma.appointment.repository.AppointmentRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class ConflictDetectionService {

    private final AppointmentRepository appointmentRepository;

    @Transactional(readOnly = true)
    public ConflictCheckResponse checkConflicts(ConflictCheckRequest request) {
        return checkConflicts(
                request.getUser1Key(), request.getUser1Type(), request.getUser1Name(),
                request.getUser2Key(), request.getUser2Type(), request.getUser2Name(),
                request.getStartDateTime(), request.getEndDateTime(),
                request.getAppointmentIdToExclude()
        );
    }

    @Transactional(readOnly = true)
    public ConflictCheckResponse checkConflicts(
            String user1Key, String user1Type, String user1Name,
            String user2Key, String user2Type, String user2Name,
            Instant startDateTime, Instant endDateTime,
            UUID appointmentIdToExclude) {

        if (startDateTime == null || endDateTime == null || !startDateTime.isBefore(endDateTime)) {
            throw new IllegalArgumentException("Invalid appointment interval: startDateTime must be before endDateTime.");
        }

        long user1Clashes = appointmentRepository.countConflictingAppointments(
                user1Key, user1Type, startDateTime, endDateTime, appointmentIdToExclude
        );
        boolean user1Busy = user1Clashes > 0;

        long user2Clashes = appointmentRepository.countConflictingAppointments(
                user2Key, user2Type, startDateTime, endDateTime, appointmentIdToExclude
        );
        boolean user2Busy = user2Clashes > 0;

        String name1 = (user1Name != null && !user1Name.isBlank()) ? user1Name : user1Key;
        String name2 = (user2Name != null && !user2Name.isBlank()) ? user2Name : user2Key;

        if (user1Busy && user2Busy) {
            String msg = String.format("Both %s and %s already have appointments scheduled during this time window.", name1, name2);
            return ConflictCheckResponse.builder()
                    .hasConflict(true)
                    .message(msg)
                    .conflictingUser("BOTH")
                    .build();
        } else if (user1Busy) {
            String msg = String.format("%s already has an appointment scheduled during this time window.", name1);
            return ConflictCheckResponse.builder()
                    .hasConflict(true)
                    .message(msg)
                    .conflictingUser(user1Key)
                    .build();
        } else if (user2Busy) {
            String msg = String.format("%s already has an appointment scheduled during this time window.", name2);
            return ConflictCheckResponse.builder()
                    .hasConflict(true)
                    .message(msg)
                    .conflictingUser(user2Key)
                    .build();
        }

        return ConflictCheckResponse.builder()
                .hasConflict(false)
                .message("No appointment conflicts found.")
                .build();
    }

    public void assertNoConflict(
            String user1Key, String user1Type, String user1Name,
            String user2Key, String user2Type, String user2Name,
            Instant startDateTime, Instant endDateTime,
            UUID appointmentIdToExclude) {

        ConflictCheckResponse response = checkConflicts(
                user1Key, user1Type, user1Name,
                user2Key, user2Type, user2Name,
                startDateTime, endDateTime,
                appointmentIdToExclude
        );

        if (response.isHasConflict()) {
            throw new ConflictException(response.getMessage());
        }
    }
}
