package com.hekma.identity.domain;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class BaseAuditEntityTest {

    @Test
    @DisplayName("UserEntity prePersist initializes all audit fields if not present")
    void userEntity_prePersist_populatesAuditFields() {
        UserEntity user = UserEntity.builder()
                .firebaseUid("fb-123")
                .email("test@hekma.com")
                .role(Role.PATIENT)
                .build();

        assertThat(user.getCreatedAt()).isNull();
        assertThat(user.getUpdatedAt()).isNull();
        assertThat(user.getCreatedBy()).isNull();
        assertThat(user.getUpdatedBy()).isNull();

        user.onPrePersist();

        assertThat(user.getCreatedAt()).isNotNull();
        assertThat(user.getUpdatedAt()).isNotNull();
        assertThat(user.getCreatedBy()).isEqualTo("SYSTEM");
        assertThat(user.getUpdatedBy()).isEqualTo("SYSTEM");
        assertThat(user.getStatus()).isEqualTo(UserStatus.ACTIVE);
    }

    @Test
    @DisplayName("PatientDetailEntity prePersist initializes audit fields and consentedAt")
    void patientDetailEntity_prePersist_populatesAuditFields() {
        PatientDetailEntity patientDetail = PatientDetailEntity.builder()
                .firstName("Sarah")
                .lastName("Connor")
                .build();

        patientDetail.onPrePersist();

        assertThat(patientDetail.getCreatedAt()).isNotNull();
        assertThat(patientDetail.getUpdatedAt()).isNotNull();
        assertThat(patientDetail.getCreatedBy()).isEqualTo("SYSTEM");
        assertThat(patientDetail.getUpdatedBy()).isEqualTo("SYSTEM");
        assertThat(patientDetail.getConsentedAt()).isNotNull();
    }

    @Test
    @DisplayName("preUpdate updates updatedAt timestamp")
    void preUpdate_updatesTimestamp() throws InterruptedException {
        UserEntity user = UserEntity.builder()
                .firebaseUid("fb-123")
                .email("test@hekma.com")
                .role(Role.PATIENT)
                .build();

        user.onPrePersist();
        Instant initialUpdatedAt = user.getUpdatedAt();

        Thread.sleep(10);
        user.onPreUpdate();

        assertThat(user.getUpdatedAt()).isAfterOrEqualTo(initialUpdatedAt);
    }

    @Test
    @DisplayName("Explicitly specified audit fields in builder are preserved")
    void builder_preservesExplicitAuditFields() {
        Instant specificInstant = Instant.parse("2026-01-01T00:00:00Z");
        UserEntity user = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-custom")
                .email("custom@hekma.com")
                .role(Role.ADMIN)
                .createdBy("admin-user")
                .updatedBy("admin-user")
                .createdAt(specificInstant)
                .updatedAt(specificInstant)
                .version(1L)
                .build();

        user.onPrePersist();

        assertThat(user.getCreatedBy()).isEqualTo("admin-user");
        assertThat(user.getUpdatedBy()).isEqualTo("admin-user");
        assertThat(user.getCreatedAt()).isEqualTo(specificInstant);
        assertThat(user.getUpdatedAt()).isEqualTo(specificInstant);
        assertThat(user.getVersion()).isEqualTo(1L);
    }
}
