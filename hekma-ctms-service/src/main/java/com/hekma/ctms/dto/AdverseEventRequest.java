package com.hekma.ctms.dto;

import com.hekma.ctms.domain.StudyPatientAdverseEventEntity;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdverseEventRequest {
    private String adverseEventId;
    private String studyId;
    private String siteId;
    @NotBlank(message = "patientId is required")
    private String patientId;
    @NotBlank(message = "aeTerm is required")
    private String aeTerm;
    private String severity;
    private String causality;
    private String outcome;
    private String startDate;
    private String stopDate;
    private String summary;
}
