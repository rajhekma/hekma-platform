package com.hekma.ctms.controller.graphql;

import com.hekma.ctms.domain.*;
import com.hekma.ctms.dto.AdverseEventRequest;
import com.hekma.ctms.dto.AdverseEventResponse;
import com.hekma.ctms.dto.ApiResponse;
import com.hekma.ctms.dto.StudyQueryRequest;
import com.hekma.ctms.dto.StudyQueryResponse;
import com.hekma.ctms.dto.StudyRequest;
import com.hekma.ctms.dto.StudyResponse;
import com.hekma.ctms.dto.StudySiteRequest;
import com.hekma.ctms.dto.StudySiteResponse;
import com.hekma.ctms.security.CtmsPrincipal;
import com.hekma.ctms.service.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

@Slf4j
@Controller
@RequiredArgsConstructor
public class StudyGraphQlController {

    private final StudyService studyService;
    private final StudySiteService studySiteService;
    private final AdverseEventService adverseEventService;
    private final StudyScheduleService studyScheduleService;

    // --- Queries ---

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public StudyResponse getStudy(@Argument String studyId, @AuthenticationPrincipal CtmsPrincipal principal) {
        return studyService.getStudy(studyId, principal);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudyResponse> getAccountStudy(@Argument String accountId, @AuthenticationPrincipal CtmsPrincipal principal) {
        return studyService.listStudies(principal);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudyResponse> getStudySearch(@Argument String searchStr, @AuthenticationPrincipal CtmsPrincipal principal) {
        return studyService.searchStudies(searchStr, principal);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudyResponse> getStudysOfSite(@Argument String siteId, @AuthenticationPrincipal CtmsPrincipal principal) {
        return studyService.listStudies(principal);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudyEventEntity> getStudyEvent(@Argument String studyId, @Argument String eventType) {
        return studyService.getStudyEvents(studyId, eventType);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudyContactEntity> getStudyContact(@Argument String studyId) {
        return studyService.getStudyContacts(studyId);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudySiteResponse> getStudySite(@Argument String studyId) {
        return studySiteService.getStudySites(studyId);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudySiteContactEntity> getStudySiteContact(@Argument String studyId, @Argument String siteId) {
        return studySiteService.getStudySiteContacts(studyId, siteId);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudyArmEntity> getStudyArms(@Argument String studyId) {
        return studyService.getStudyArms(studyId);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public Map<String, Object> getStudyArmsWithDetails(@Argument String armNum) {
        List<StudyArmDetailEntity> details = studyService.getStudyArmDetails(armNum);
        return Map.of("details", details);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('adverse_event:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<AdverseEventResponse> getStudySiteAdverseEvents(@Argument String studyId, @Argument String siteId) {
        return adverseEventService.getStudySiteAdverseEvents(studyId, siteId);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('adverse_event:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<AdverseEventResponse> getStudyAdverseEvents(@Argument String studyId) {
        return adverseEventService.getStudyAdverseEvents(studyId);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('query:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public List<StudyQueryResponse> searchStudySiteQuery(@Argument String queryId, @Argument String queryNum,
                                                         @Argument String studyId, @Argument String siteId,
                                                         @Argument String statuses, @Argument String assignedTo) {
        if (queryId != null && !queryId.isBlank() && !"*".equals(queryId)) {
            return List.of(studySiteService.getStudySiteQuery(queryId));
        }
        return studySiteService.getStudySiteQueries(studyId, siteId);
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('study:read') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public Map<String, Object> getScheduleDetails(@Argument String studyId, @Argument String scheduleId) {
        return studyScheduleService.getScheduleDetails(studyId, scheduleId);
    }

    // --- Mutations ---

    @MutationMapping
    @PreAuthorize("hasAuthority('study:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> createStudy(@Argument String studyNumber, @Argument String parentAccountId,
                                           @Argument String studyTitle, @Argument String nameofIMP,
                                           @Argument String devPhase, @Argument String status,
                                           @Argument String primaryEndPoint, @Argument String secondaryEndPoint,
                                           @Argument String expEndPoint, @Argument String startDt,
                                           @Argument String endDt, @Argument String studyDuration,
                                           @Argument String stoppingCriteria, @Argument String numberOfSitesPlanned,
                                           @Argument String numberOfSubPlanned, @Argument String route,
                                           @Argument String regiman, @Argument String dosage,
                                           @Argument String statMethod, @Argument String interimAnalysis,
                                           @Argument String studyFlow, @Argument String protocolNumber,
                                           @Argument String studyStatus, @Argument String studyType,
                                           @Argument String studyPhase, @Argument String sponsorType,
                                           @Argument String indication, @Argument String therapeuticArea,
                                           @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyRequest req = StudyRequest.builder()
                .studyNumber(studyNumber)
                .parentAccountId(parentAccountId != null ? Long.parseLong(parentAccountId) : null)
                .studyTitle(studyTitle)
                .nameOfImp(nameofIMP)
                .devPhase(devPhase)
                .status(status)
                .primaryEndPoint(primaryEndPoint)
                .secondaryEndPoint(secondaryEndPoint)
                .expEndPoint(expEndPoint)
                .studyDuration(studyDuration)
                .stoppingCriteria(stoppingCriteria)
                .numberOfSitesPlanned(numberOfSitesPlanned)
                .numberOfSubPlanned(numberOfSubPlanned)
                .route(route)
                .regiman(regiman)
                .dosage(dosage)
                .statMethod(statMethod)
                .interimAnalysis(interimAnalysis)
                .studyFlow(studyFlow)
                .protocolNumber(protocolNumber)
                .studyStatus(studyStatus)
                .studyType(studyType)
                .studyPhase(studyPhase)
                .sponsorType(sponsorType)
                .indication(indication)
                .therapeuticArea(therapeuticArea)
                .build();
        StudyResponse res = studyService.createStudy(req, principal);
        return ApiResponse.ok("Study created", res.getStudyId());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('study:update') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> updateStudy(@Argument String studyId, @Argument String studyNumber,
                                           @Argument String studyTitle, @Argument String nameofIMP,
                                           @Argument String devPhase, @Argument String status,
                                           @Argument String primaryEndPoint, @Argument String secondaryEndPoint,
                                           @Argument String expEndPoint, @Argument String startDt,
                                           @Argument String endDt, @Argument String stoppingCriteria,
                                           @Argument String indication, @Argument String therapeuticArea,
                                           @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyRequest req = StudyRequest.builder()
                .studyTitle(studyTitle)
                .nameOfImp(nameofIMP)
                .devPhase(devPhase)
                .status(status)
                .primaryEndPoint(primaryEndPoint)
                .secondaryEndPoint(secondaryEndPoint)
                .expEndPoint(expEndPoint)
                .stoppingCriteria(stoppingCriteria)
                .indication(indication)
                .therapeuticArea(therapeuticArea)
                .build();
        StudyResponse res = studyService.updateStudy(studyId, req, principal);
        return ApiResponse.ok("Study updated", res.getStudyId());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('site:manage') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> addStudySite(@Argument String studyId, @Argument String siteId,
                                            @Argument String siteName, @Argument String siteUserId,
                                            @Argument String status, @Argument String onboardStatus,
                                            @Argument String limitization, @Argument String pContact,
                                            @Argument String role, @Argument String impReceived,
                                            @Argument String placeholder,
                                            @AuthenticationPrincipal CtmsPrincipal principal) {
        StudySiteRequest req = StudySiteRequest.builder()
                .studyId(studyId)
                .siteId(siteId)
                .siteName(siteName)
                .siteUserId(siteUserId)
                .status(status)
                .onboardStatus(onboardStatus)
                .limitization(limitization)
                .primaryContact(pContact)
                .role(role)
                .impReceived(impReceived)
                .placeholder(placeholder)
                .build();
        StudySiteResponse res = studySiteService.addStudySite(req, principal);
        return ApiResponse.ok("Site added to study", res.getSiteId());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('site:manage') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> addStudySiteContact(@Argument String studyId, @Argument String siteId,
                                                   @Argument String contactId, @Argument String role,
                                                   @Argument String primaryContactInd) {
        studySiteService.addStudySiteContact(studyId, siteId, contactId, role, primaryContactInd);
        return ApiResponse.ok("Contact added to study site", contactId);
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('study:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> addStudyArm(@Argument String armName, @Argument String studyId,
                                           @Argument String type, @Argument String description,
                                           @Argument String status,
                                           @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyArmEntity arm = studyService.addStudyArm(armName, studyId, type, description, status, principal);
        return ApiResponse.ok("Study arm added", arm.getArmNum());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('study:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> createStudyEvent(@Argument String studyId, @Argument String eventType,
                                                @Argument String type, @Argument String description,
                                                @Argument String severity, @Argument String status,
                                                @Argument String effectiveDate,
                                                @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyEventEntity event = studyService.createStudyEvent(studyId, eventType, type, description, severity, status, effectiveDate, principal);
        return ApiResponse.ok("Study event created", event.getEventId());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('adverse_event:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> createStudySitePatientAdverseEvents(
            @Argument String studyId, @Argument String siteId, @Argument String patientId,
            @Argument String aeTerm, @Argument String severity, @Argument String causality,
            @Argument String outcome, @Argument String startDate, @Argument String stopDate,
            @Argument String summary, @AuthenticationPrincipal CtmsPrincipal principal) {
        AdverseEventRequest req = AdverseEventRequest.builder()
                .studyId(studyId)
                .siteId(siteId)
                .patientId(patientId)
                .aeTerm(aeTerm)
                .severity(severity)
                .causality(causality)
                .outcome(outcome)
                .startDate(startDate)
                .stopDate(stopDate)
                .summary(summary)
                .build();
        AdverseEventResponse res = adverseEventService.createAdverseEvent(req, principal);
        return ApiResponse.ok("Adverse event created", res.getAdverseEventId());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('adverse_event:update') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> updateStudySitePatientAdverseEvents(
            @Argument String adverseEventId, @Argument String studyId, @Argument String siteId,
            @Argument String patientId, @Argument String aeTerm, @Argument String severity,
            @Argument String causality, @Argument String outcome, @Argument String startDate,
            @Argument String stopDate, @Argument String summary,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        AdverseEventRequest req = AdverseEventRequest.builder()
                .studyId(studyId)
                .siteId(siteId)
                .patientId(patientId)
                .aeTerm(aeTerm)
                .severity(severity)
                .causality(causality)
                .outcome(outcome)
                .startDate(startDate)
                .stopDate(stopDate)
                .summary(summary)
                .build();
        AdverseEventResponse res = adverseEventService.updateAdverseEvent(adverseEventId, req, principal);
        return ApiResponse.ok("Adverse event updated", res.getAdverseEventId());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('adverse_event:delete') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> deletePatientAdverseEvents(@Argument String adverseEventId) {
        adverseEventService.deleteAdverseEvent(adverseEventId);
        return ApiResponse.ok("Adverse event deleted", adverseEventId);
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('query:create') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> addStudySiteQuery(
            @Argument String studyId, @Argument String studyName, @Argument String siteId,
            @Argument String queryTitle, @Argument String queryDescription, @Argument String category,
            @Argument String severity, @Argument String assignedTo, @Argument String assignedToName,
            @Argument String sponsorReference1, @Argument String sponsorReference2,
            @AuthenticationPrincipal CtmsPrincipal principal) {
        StudyQueryRequest req = StudyQueryRequest.builder()
                .studyId(studyId)
                .studyName(studyName)
                .siteId(siteId)
                .queryTitle(queryTitle)
                .queryDescription(queryDescription)
                .category(category)
                .severity(severity)
                .assignedTo(assignedTo)
                .assignedToName(assignedToName)
                .sponsorReference1(sponsorReference1)
                .sponsorReference2(sponsorReference2)
                .build();
        StudyQueryResponse res = studySiteService.addStudySiteQuery(req, principal);
        return ApiResponse.ok("Study query added", res.getQueryId());
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('query:update') or hasRole('ADMIN') or hasRole('SYSTEM_ADMIN')")
    public ApiResponse<String> resolveStudySiteQuery(@Argument String queryId) {
        StudyQueryResponse res = studySiteService.resolveStudySiteQuery(queryId);
        return ApiResponse.ok("Query resolved", res.getQueryId());
    }
}
