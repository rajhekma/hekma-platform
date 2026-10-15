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
@Table(name = "ctms_study_schedule_events")
@SQLRestriction("is_deleted = false")
public class StudyScheduleEventEntity extends BaseAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "schedule_id", nullable = false, length = 100)
    private String scheduleId;

    @Column(name = "event_id", nullable = false, length = 100)
    private String eventId;

    @Column(name = "event_name")
    private String eventName;

    @Column(name = "segment_id", length = 100)
    private String segmentId;

    @Column(name = "row_num")
    private Integer rowNum;

    @Column(name = "col_num")
    private Integer colNum;
}
