package com.hekma.ctms.dto;

import com.hekma.ctms.domain.StudySiteEntity;
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
public class StudySiteRequest {
    private String studyId;
    @NotBlank(message = "siteId is required")
    private String siteId;
    private String siteName;
    private String siteUserId;
    private String status;
    private String onboardStatus;
    private String limitization;
    private String primaryContact;
    private String role;
    private String impReceived;
    private String placeholder;
}
