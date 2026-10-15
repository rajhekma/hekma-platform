package com.hekma.appointment.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;
import org.hibernate.annotations.SQLRestriction;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "appointment_requests")
@SQLRestriction("is_deleted = false")
@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@AllArgsConstructor
public class AppointmentRequestEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "tenant_path", nullable = false, length = 255)
    private String tenantPath;

    @Column(name = "from_key", nullable = false, length = 100)
    private String fromKey;

    @Column(name = "from_type", nullable = false, length = 50)
    private String fromType;

    @Column(name = "to_key", nullable = false, length = 100)
    private String toKey;

    @Column(name = "to_type", nullable = false, length = 50)
    private String toType;

    @Column(name = "ref_key1", length = 100)
    private String refKey1;

    @Column(name = "ref_type1", length = 50)
    private String refType1;

    @Column(name = "ref_key2", length = 100)
    private String refKey2;

    @Column(name = "ref_type2", length = 50)
    private String refType2;

    @Column(name = "ref_key3", length = 100)
    private String refKey3;

    @Column(name = "ref_type3", length = 50)
    private String refType3;

    @Enumerated(EnumType.STRING)
    @Column(name = "type", nullable = false, length = 50)
    private RequestType type;

    @Column(name = "request_timestamp", nullable = false)
    @Builder.Default
    private Instant requestTimestamp = Instant.now();

    @Column(name = "request_description", columnDefinition = "TEXT")
    private String requestDescription;

    @Enumerated(EnumType.STRING)
    @Column(name = "request_status", nullable = false, length = 50)
    @Builder.Default
    private RequestStatus requestStatus = RequestStatus.CREATED;

    @Column(name = "request_response", columnDefinition = "TEXT")
    private String requestResponse;

    @Column(name = "request_update_timestamp")
    private Instant requestUpdateTimestamp;
}
