package com.hekma.ctms.controller.webhook;

import com.hekma.ctms.dto.ApiResponse;
import com.hekma.ctms.dto.CmtsWebhookPayload;
import com.hekma.ctms.service.CmtsWebhookService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Slf4j
@RestController
@RequiredArgsConstructor
@Tag(name = "EDC Webhooks", description = "Clinical data ingestion and keys for Electronic Data Capture (EDC)")
public class CmtsWebhookController {

    private final CmtsWebhookService webhookService;

    @PostMapping("/webhook/cmts/generate-keys")
    @Operation(summary = "Generate or retrieve EDC access credentials for a Study and Site")
    public ResponseEntity<ApiResponse<Map<String, String>>> generateKeys(
            @RequestParam String studyId,
            @RequestParam String siteId,
            @RequestParam(required = false, defaultValue = "admin") String createdBy) {
        log.info("Generating EDC webhook keys for studyId={}, siteId={}", studyId, siteId);
        Map<String, String> keys = webhookService.generateKeys(studyId, siteId, createdBy);
        return ResponseEntity.ok(ApiResponse.ok("Keys generated successfully", keys));
    }

    @PostMapping("/webhook/cmts")
    @Operation(summary = "Ingest clinical trial events from external EDC systems")
    public ResponseEntity<ApiResponse<String>> receiveWebhook(
            @RequestHeader("X-Access-Key") String accessKey,
            @RequestHeader("X-Secret-Key") String secretKey,
            @RequestBody CmtsWebhookPayload payload) {
        log.info("Received EDC webhook payload for resource: {}, study: {}, site: {}",
                payload.getResourceType(), payload.getStudyId(), payload.getSiteId());
        ApiResponse<String> response = webhookService.processWebhook(accessKey, secretKey, payload);
        return ResponseEntity.status(response.getCode()).body(response);
    }

    @GetMapping("/api/v1/webhook/cmts/load_data")
    @Operation(summary = "Fetch resource data for bound EDC client credentials")
    public ResponseEntity<ApiResponse<Object>> loadData(
            @RequestHeader("X-Access-Key") String accessKey,
            @RequestHeader("X-Secret-Key") String secretKey,
            @RequestParam String resourceType,
            @RequestParam(required = false) String studyId,
            @RequestParam(required = false) String siteId,
            @RequestParam(required = false) String scheduleId,
            @RequestParam(required = false) String eventType,
            @RequestParam(required = false) String patientId,
            @RequestParam(required = false) String armNum,
            @RequestParam(required = false) String noteId,
            @RequestParam(required = false) String noteType,
            @RequestParam(required = false) String queryId,
            @RequestParam(required = false) String statuses,
            @RequestParam(required = false) String assignedTo) {
        log.info("Received EDC load_data request for resourceType: {}", resourceType);
        ApiResponse<Object> response = webhookService.loadData(
                accessKey, secretKey, resourceType, studyId, siteId, scheduleId,
                eventType, patientId, armNum, noteId, noteType, queryId, statuses, assignedTo);
        return ResponseEntity.status(response.getCode()).body(response);
    }
}
