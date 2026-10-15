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
@Table(name = "ctms_study_arm_details")
@SQLRestriction("is_deleted = false")
public class StudyArmDetailEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "arm_num", nullable = false, length = 100)
    private String armNum;

    @Column(name = "dosage_name")
    private String dosageName;

    @Column(name = "dosage")
    private String dosage;

    @Column(name = "strength", length = 100)
    private String strength;

    @Column(name = "unit", length = 50)
    private String unit;

    @Column(name = "route", length = 100)
    private String route;

    @Column(name = "frequency", length = 100)
    private String frequency;

    @Column(name = "description", columnDefinition = "TEXT")
    private String description;
}
