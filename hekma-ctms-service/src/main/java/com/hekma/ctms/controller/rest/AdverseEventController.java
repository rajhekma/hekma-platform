package com.hekma.ctms.controller.rest;

import com.hekma.ctms.dto.AdverseEventRequest;
import com.hekma.ctms.dto.AdverseEventResponse;
import com.hekma.ctms.dto.ApiResponse;
import com.hekma.ctms.security.CtmsPrincipal;
import com.hekma.ctms.service.AdverseEventService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/studies")
@RequiredArgsConstructor
@Tag(name = "Adverse Events", description = "Endpoints for logging, updating, and reviewing adverse events")
public class AdverseEventController {

    private final AdverseEventService adverseEventService;

    @PostMapping("/{studyId}/sites/{siteId}/adverse-events")
    @PreAuthorize("hasAuthority('adverse_event:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Log an adverse event for a study patient")
    public ResponseEntity<ApiResponse<AdverseEventResponse>> logAdverseEvent(
            @PathVariable String studyId,
            @PathVariable String siteId,
            @Valid @RequestBody AdverseEventRequest request,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        request.setStudyId(studyId);
        request.setSiteId(siteId);
        AdverseEventResponse response = adverseEventService.createAdverseEvent(request, principal);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok("Adverse event logged successfully", response));
    }

    @PutMapping("/adverse-events/{aeId}")
    @PreAuthorize("hasAuthority('adverse_event:update') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Update an existing adverse event")
    public ResponseEntity<ApiResponse<AdverseEventResponse>> updateAdverseEvent(
            @PathVariable String aeId,
            @RequestBody AdverseEventRequest request,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        AdverseEventResponse response = adverseEventService.updateAdverseEvent(aeId, request, principal);
        return ResponseEntity.ok(ApiResponse.ok("Adverse event updated", response));
    }

    @GetMapping("/{studyId}/adverse-events")
    @PreAuthorize("hasAuthority('adverse_event:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "List all adverse events for a study across all sites")
    public ResponseEntity<ApiResponse<List<AdverseEventResponse>>> getStudyAdverseEvents(@PathVariable String studyId) {
        return ResponseEntity.ok(ApiResponse.ok(adverseEventService.getStudyAdverseEvents(studyId)));
    }

    @GetMapping("/{studyId}/sites/{siteId}/adverse-events")
    @PreAuthorize("hasAuthority('adverse_event:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "List adverse events for a specific site in a study")
    public ResponseEntity<ApiResponse<List<AdverseEventResponse>>> getSiteAdverseEvents(
            @PathVariable String studyId,
            @PathVariable String siteId) {
        return ResponseEntity.ok(ApiResponse.ok(adverseEventService.getStudySiteAdverseEvents(studyId, siteId)));
    }

    @GetMapping("/adverse-events/{aeId}")
    @PreAuthorize("hasAuthority('adverse_event:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get single adverse event by ID")
    public ResponseEntity<ApiResponse<AdverseEventResponse>> getAdverseEvent(@PathVariable String aeId) {
        return ResponseEntity.ok(ApiResponse.ok(adverseEventService.getAdverseEvent(aeId)));
    }

    @DeleteMapping("/adverse-events/{aeId}")
    @PreAuthorize("hasAuthority('adverse_event:delete') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Delete an adverse event")
    public ResponseEntity<ApiResponse<Void>> deleteAdverseEvent(@PathVariable String aeId) {
        adverseEventService.deleteAdverseEvent(aeId);
        return ResponseEntity.ok(ApiResponse.ok("Adverse event deleted", null));
    }
}
