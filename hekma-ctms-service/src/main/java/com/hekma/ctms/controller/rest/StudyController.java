package com.hekma.ctms.controller.rest;

import com.hekma.ctms.domain.StudyArmDetailEntity;
import com.hekma.ctms.domain.StudyArmEntity;
import com.hekma.ctms.domain.StudyContactEntity;
import com.hekma.ctms.domain.StudyEventEntity;
import com.hekma.ctms.dto.ApiResponse;
import com.hekma.ctms.dto.StudyRequest;
import com.hekma.ctms.dto.StudyResponse;
import com.hekma.ctms.security.CtmsPrincipal;
import com.hekma.ctms.service.StudyService;
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
@Tag(name = "Studies", description = "Clinical study protocols and metadata management")
public class StudyController {

    private final StudyService studyService;

    @PostMapping
    @PreAuthorize("hasAuthority('study:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Create a new clinical study protocol")
    public ResponseEntity<ApiResponse<StudyResponse>> createStudy(
            @Valid @RequestBody StudyRequest request,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyResponse response = studyService.createStudy(request, principal);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok("Study created successfully", response));
    }

    @PutMapping("/{studyId}")
    @PreAuthorize("hasAuthority('study:update') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Update an existing clinical study")
    public ResponseEntity<ApiResponse<StudyResponse>> updateStudy(
            @PathVariable String studyId,
            @RequestBody StudyRequest request,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyResponse response = studyService.updateStudy(studyId, request, principal);
        return ResponseEntity.ok(ApiResponse.ok("Study updated successfully", response));
    }

    @GetMapping("/{studyId}")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get study details by ID or study number")
    public ResponseEntity<ApiResponse<StudyResponse>> getStudy(
            @PathVariable String studyId,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyResponse response = studyService.getStudy(studyId, principal);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }

    @GetMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "List or search all studies visible to current organization")
    public ResponseEntity<ApiResponse<List<StudyResponse>>> listStudies(
            @RequestParam(required = false) String search,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        List<StudyResponse> list = studyService.searchStudies(search, principal);
        return ResponseEntity.ok(ApiResponse.ok(list));
    }

    // --- Study Arms ---
    @GetMapping("/{studyId}/arms")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get study arms for a study")
    public ResponseEntity<ApiResponse<List<StudyArmEntity>>> getStudyArms(@PathVariable String studyId) {
        return ResponseEntity.ok(ApiResponse.ok(studyService.getStudyArms(studyId)));
    }

    @GetMapping("/arms/{armNum}/details")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get arm details by arm number")
    public ResponseEntity<ApiResponse<List<StudyArmDetailEntity>>> getStudyArmDetails(@PathVariable String armNum) {
        return ResponseEntity.ok(ApiResponse.ok(studyService.getStudyArmDetails(armNum)));
    }

    // --- Study Events ---
    @GetMapping("/{studyId}/events")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get inclusion/exclusion criteria or study events")
    public ResponseEntity<ApiResponse<List<StudyEventEntity>>> getStudyEvents(
            @PathVariable String studyId,
            @RequestParam(required = false) String eventType) {
        return ResponseEntity.ok(ApiResponse.ok(studyService.getStudyEvents(studyId, eventType)));
    }

    // --- Study Contacts ---
    @GetMapping("/{studyId}/contacts")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get study personnel and contacts")
    public ResponseEntity<ApiResponse<List<StudyContactEntity>>> getStudyContacts(@PathVariable String studyId) {
        return ResponseEntity.ok(ApiResponse.ok(studyService.getStudyContacts(studyId)));
    }
}
