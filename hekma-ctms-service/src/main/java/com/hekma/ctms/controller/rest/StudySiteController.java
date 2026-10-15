package com.hekma.ctms.controller.rest;

import com.hekma.ctms.domain.StudySiteContactEntity;
import com.hekma.ctms.domain.StudySiteNoteEntity;
import com.hekma.ctms.dto.*;
import com.hekma.ctms.security.CtmsPrincipal;
import com.hekma.ctms.service.StudySiteService;
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
@Tag(name = "Study Sites", description = "Study-site allocations, site personnel, notes, and queries")
public class StudySiteController {

    private final StudySiteService studySiteService;

    @PostMapping("/{studyId}/sites")
    @PreAuthorize("hasAuthority('site:manage') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Allocate a site to a clinical study")
    public ResponseEntity<ApiResponse<StudySiteResponse>> addStudySite(
            @PathVariable String studyId,
            @Valid @RequestBody StudySiteRequest request,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        request.setStudyId(studyId);
        StudySiteResponse response = studySiteService.addStudySite(request, principal);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok("Site added to study", response));
    }

    @PutMapping("/{studyId}/sites/{siteId}")
    @PreAuthorize("hasAuthority('site:manage') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Update study-site configuration or status")
    public ResponseEntity<ApiResponse<StudySiteResponse>> updateStudySite(
            @PathVariable String studyId,
            @PathVariable String siteId,
            @RequestBody StudySiteRequest request,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        request.setStudyId(studyId);
        request.setSiteId(siteId);
        StudySiteResponse response = studySiteService.updateStudySite(request, principal);
        return ResponseEntity.ok(ApiResponse.ok("Study site updated", response));
    }

    @GetMapping("/{studyId}/sites")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get all sites allocated to a study")
    public ResponseEntity<ApiResponse<List<StudySiteResponse>>> getStudySites(@PathVariable String studyId) {
        return ResponseEntity.ok(ApiResponse.ok(studySiteService.getStudySites(studyId)));
    }

    @GetMapping("/{studyId}/sites/{siteId}")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get details of a specific site in a study")
    public ResponseEntity<ApiResponse<StudySiteResponse>> getStudySite(
            @PathVariable String studyId,
            @PathVariable String siteId) {
        return ResponseEntity.ok(ApiResponse.ok(studySiteService.getStudySite(studyId, siteId)));
    }

    // --- Contacts ---
    @GetMapping("/{studyId}/sites/{siteId}/contacts")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get personnel assigned to a study site")
    public ResponseEntity<ApiResponse<List<StudySiteContactEntity>>> getSiteContacts(
            @PathVariable String studyId,
            @PathVariable String siteId) {
        return ResponseEntity.ok(ApiResponse.ok(studySiteService.getStudySiteContacts(studyId, siteId)));
    }

    // --- Queries ---
    @GetMapping("/{studyId}/sites/{siteId}/queries")
    @PreAuthorize("hasAuthority('query:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get queries for a study site")
    public ResponseEntity<ApiResponse<List<StudyQueryResponse>>> getSiteQueries(
            @PathVariable String studyId,
            @PathVariable String siteId) {
        return ResponseEntity.ok(ApiResponse.ok(studySiteService.getStudySiteQueries(studyId, siteId)));
    }

    @PostMapping("/{studyId}/sites/{siteId}/queries")
    @PreAuthorize("hasAuthority('query:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Raise a new query for a study site")
    public ResponseEntity<ApiResponse<StudyQueryResponse>> createQuery(
            @PathVariable String studyId,
            @PathVariable String siteId,
            @Valid @RequestBody StudyQueryRequest request,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        request.setStudyId(studyId);
        request.setSiteId(siteId);
        StudyQueryResponse response = studySiteService.addStudySiteQuery(request, principal);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok("Query created successfully", response));
    }

    @PutMapping("/queries/{queryId}/resolve")
    @PreAuthorize("hasAuthority('query:update') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Resolve a study site query")
    public ResponseEntity<ApiResponse<StudyQueryResponse>> resolveQuery(@PathVariable String queryId) {
        return ResponseEntity.ok(ApiResponse.ok("Query resolved successfully", studySiteService.resolveStudySiteQuery(queryId)));
    }

    // --- Notes ---
    @GetMapping("/{studyId}/sites/{siteId}/notes")
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get notes recorded for a study site")
    public ResponseEntity<ApiResponse<List<StudySiteNoteEntity>>> getSiteNotes(
            @PathVariable String studyId,
            @PathVariable String siteId) {
        return ResponseEntity.ok(ApiResponse.ok(studySiteService.getStudySiteNotes(studyId, siteId)));
    }
}
