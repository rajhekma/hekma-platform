package com.hekma.ctms.domain;

import com.hekma.ctms.domain.common.BaseAuditEntity;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.experimental.SuperBuilder;
import org.hibernate.annotations.SQLRestriction;

@Getter
@Setter
@SuperBuilder
@NoArgsConstructor
@Entity
@Table(name = "ctms_support_details")
@SQLRestriction("is_deleted = false")
public class SupportDetailEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "support_id", length = 100)
    private String supportId;

    @Column(name = "bu_area", length = 100)
    private String buArea;

    @Column(name = "bu_id", length = 100)
    private String buId;

    @Column(name = "type", length = 100)
    private String type;

    @Column(name = "status", length = 50)
    private String status;

    @Column(name = "detail1", columnDefinition = "TEXT")
    private String detail1;

    @Column(name = "detail2", columnDefinition = "TEXT")
    private String detail2;

    @Column(name = "detail3", columnDefinition = "TEXT")
    private String detail3;

    @Column(name = "detail4", columnDefinition = "TEXT")
    private String detail4;
}
