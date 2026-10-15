package com.hekma.identity.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "identity_patient_details")
@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@AllArgsConstructor
public class PatientDetailEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private UserEntity user;

    @Column(name = "first_name", nullable = false, length = 100)
    private String firstName;

    @Column(name = "last_name", nullable = false, length = 100)
    private String lastName;

    @Column(name = "phone_number", length = 50)
    private String phoneNumber;

    @Column(name = "invitation_code", length = 100)
    private String invitationCode;

    @Column(name = "terms_accepted", nullable = false)
    @Builder.Default
    private boolean termsAccepted = false;

    @Column(name = "privacy_policy_accepted", nullable = false)
    @Builder.Default
    private boolean privacyPolicyAccepted = false;

    @Column(name = "health_data_consent_accepted", nullable = false)
    @Builder.Default
    private boolean healthDataConsentAccepted = false;

    @Column(name = "consented_at", nullable = false)
    private Instant consentedAt;

    @jakarta.persistence.ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assigned_user_id")
    private UserEntity assignedUser;

    /**
     * When the invitation code stops being valid (72 hours after the invitation). Null for legacy invitations.
     */
    @Column(name = "invitation_expires_at")
    private Instant invitationExpiresAt;

    /**
     * When the invitation code was redeemed; a used code cannot be redeemed again.
     */
    @Column(name = "invitation_used_at")
    private Instant invitationUsedAt;

    public UUID getAssignedUserId() {
        return assignedUser != null ? assignedUser.getId() : null;
    }


    @PrePersist
    @Override
    public void onPrePersist() {
        super.onPrePersist();
        if (this.consentedAt == null) {
            this.consentedAt = Instant.now();
        }
    }
}
