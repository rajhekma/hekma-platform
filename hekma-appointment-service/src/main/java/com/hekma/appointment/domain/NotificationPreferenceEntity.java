package com.hekma.appointment.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;
import org.hibernate.annotations.SQLRestriction;

import java.util.UUID;

@Entity
@Table(
        name = "appointment_user_preferences",
        uniqueConstraints = @UniqueConstraint(name = "appointment_uq_user_pref", columnNames = {"user_id", "user_type"})
)
@SQLRestriction("is_deleted = false")
@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@AllArgsConstructor
public class NotificationPreferenceEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "user_id", nullable = false, length = 100)
    private String userId;

    @Column(name = "user_type", nullable = false, length = 50)
    private String userType;

    @Column(name = "toggle_in_app", nullable = false)
    @Builder.Default
    private boolean toggleInApp = true;

    @Column(name = "toggle_email", nullable = false)
    @Builder.Default
    private boolean toggleEmail = true;

    @Column(name = "toggle_message", nullable = false)
    @Builder.Default
    private boolean toggleMessage = false;
}
