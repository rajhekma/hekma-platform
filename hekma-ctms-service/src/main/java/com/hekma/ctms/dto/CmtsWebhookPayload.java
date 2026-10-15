package com.hekma.ctms.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CmtsWebhookPayload {
    private String resourceType;
    private String studyId;
    private String siteId;
    private String patientId;
    private String adverseEventId;
    private String scheduleId;
    private Map<String, Object> data;
}
