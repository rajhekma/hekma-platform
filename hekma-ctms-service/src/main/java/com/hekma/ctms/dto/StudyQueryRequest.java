package com.hekma.ctms.dto;

import com.hekma.ctms.domain.StudySiteQueryEntity;
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
public class StudyQueryRequest {
    private String queryId;
    private String queryNum;
    @NotBlank(message = "studyId is required")
    private String studyId;
    private String studyName;
    @NotBlank(message = "siteId is required")
    private String siteId;
    @NotBlank(message = "queryTitle is required")
    private String queryTitle;
    private String queryDescription;
    private String category;
    private String severity;
    private String status;
    private String assignedTo;
    private String assignedToName;
    private String sponsorReference1;
    private String sponsorReference2;
    private String siteReference1;
    private String siteReference2;
    private String createdByName;
    private String queryResponse;
}
