package com.hekma.identity.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AllArgsConstructor;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;

import java.util.UUID;

/**
 * One authority granted to one SPONSOR/SITE user.
 */
@Entity
@Table(name = "identity_user_authorities",
        uniqueConstraints = @UniqueConstraint(name = "identity_uq_user_authorities", columnNames = {"user_id", "authority_key"}))
@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@AllArgsConstructor
@EqualsAndHashCode(onlyExplicitlyIncluded = true, callSuper = false)
public class UserAuthorityEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @EqualsAndHashCode.Include
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private UserEntity user;

    @Convert(converter = AuthorityConverter.class)
    @Column(name = "authority_key", nullable = false, length = 64)
    private Authority authority;

    /**
     * User who granted the authority; null for system grants (registration, backfill).
     */
    @Column(name = "granted_by")
    private UUID grantedBy;
}
