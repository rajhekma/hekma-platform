package com.hekma.notification.support.domain.entity;

import jakarta.persistence.*;
import lombok.Data;

import java.util.Date;

@Data
@Entity
@Table(name = "notification_support_otp_verification")
public class SupportOtpVerificationEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false)
    private String email;

    @Column(name = "otp_hash", nullable = false, length = 128)
    private String otpHash;

    @Column(name = "challenge_id", unique = true, nullable = false, length = 36)
    private String challengeId;

    @Column(name = "attempts", nullable = false)
    private Integer attempts = 0;

    @Column(name = "verified", nullable = false)
    private Boolean verified = false;

    @Column(name = "session_token", length = 64)
    private String sessionToken;

    @Column(name = "expires_at", nullable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date expiresAt;

    @Column(name = "created_ts", nullable = false, updatable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdTs;

    @PrePersist
    protected void onCreate() {
        if (createdTs == null) {
            createdTs = new Date();
        }
        if (attempts == null) {
            attempts = 0;
        }
        if (verified == null) {
            verified = false;
        }
    }
}
