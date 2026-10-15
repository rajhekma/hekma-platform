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
@Table(name = "ctms_study_schedule_segments")
@SQLRestriction("is_deleted = false")
public class StudyScheduleSegmentEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "schedule_id", nullable = false, length = 100)
    private String scheduleId;

    @Column(name = "segment_id", nullable = false, length = 100)
    private String segmentId;

    @Column(name = "segment_name")
    private String segmentName;

    @Column(name = "segment_order")
    private Integer segmentOrder;
}
