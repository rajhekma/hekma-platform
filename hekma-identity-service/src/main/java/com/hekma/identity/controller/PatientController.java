package com.hekma.identity.controller;

import com.hekma.identity.dto.ApiErrorResponse;
import com.hekma.identity.dto.patient.PatientAcceptInviteRequest;
import com.hekma.identity.dto.patient.PatientAssignRequest;
import com.hekma.identity.dto.patient.PatientInviteRequest;
import com.hekma.identity.dto.patient.PatientInviteResponse;
import com.hekma.identity.dto.patient.PatientResponse;
import com.hekma.identity.security.HekmaPrincipal;
import com.hekma.identity.service.PatientService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/patients")
@Tag(name = "Patient Management", description = "Endpoints for clinical patient recruitment, invitations, acceptance, and investigator assignment")
public class PatientController {

    private final PatientService patientService;

    public PatientController(PatientService patientService) {
        this.patientService = patientService;
    }

    @PostMapping("/invite")
    @Operation(
            summary = "Invite a patient to a clinical study (SPONSOR or SITE)",
            description = "Creates a staged patient profile, maps assigned_user_id to the caller, adopts the caller's tenant, and dispatches an invitation email."
    )
    @RequestBody(
            description = "Patient invitation payload",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = PatientInviteRequest.class),
                    examples = @ExampleObject(
                            name = "Patient Invite Example",
                            value = "{\n  \"firstName\": \"Jane\",\n  \"lastName\": \"Doe\",\n  \"email\": \"jane.doe@example.com\",\n  \"phoneNumber\": \"+15551234567\",\n  \"clinicalStudyId\": \"STUDY-ONCOLOGY-01\"\n}"
                    )
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "201",
                    description = "Patient successfully invited",
                    content = @Content(schema = @Schema(implementation = PatientInviteResponse.class))
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Validation failure or email already registered",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "Caller is not authorized to invite patients or tenant is suspended",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    @PreAuthorize("hasAnyRole('SPONSOR', 'SITE') and hasAuthority('patient:create')")
    public ResponseEntity<PatientInviteResponse> invitePatient(
            @Valid @org.springframework.web.bind.annotation.RequestBody PatientInviteRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        PatientInviteResponse response = patientService.invitePatient(request, caller.userId());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PostMapping("/accept-invite")
    @Operation(
            summary = "Accept a clinical study invitation and activate account (Public)",
            description = "Validates the invitation token/code, records regulatory consents (Terms, Privacy, Health Data), creates Firebase credentials, and activates the patient profile."
    )
    @RequestBody(
            description = "Patient invite acceptance payload",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = PatientAcceptInviteRequest.class),
                    examples = @ExampleObject(
                            name = "Accept Invite Example",
                            value = "{\n  \"invitationToken\": \"INV-A1B2C3D4E5\",\n  \"password\": \"SecurePass123!\",\n  \"termsAccepted\": true,\n  \"privacyPolicyAccepted\": true,\n  \"healthDataConsentAccepted\": true\n}"
                    )
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "Patient account successfully activated",
                    content = @Content(schema = @Schema(implementation = PatientResponse.class))
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Invalid or expired invitation token, or required consents missing",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "Tenant organization suspended",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    public ResponseEntity<PatientResponse> acceptInvite(
            @Valid @org.springframework.web.bind.annotation.RequestBody PatientAcceptInviteRequest request) {
        PatientResponse response = patientService.acceptInvite(request);
        return ResponseEntity.ok(response);
    }

    @GetMapping
    @Operation(
            summary = "List patients with role-based scoping",
            description = "Returns paginated list of patients. SPONSOR and SITE users are strictly scoped to their tenant. " +
                    "Pass `assignedToMe=true` to retrieve only patients assigned directly to the caller."
    )
    @PreAuthorize("hasRole('PATIENT') or hasAuthority('patient:read')")
    public ResponseEntity<com.hekma.identity.dto.PagedResponse<PatientResponse>> listPatients(
            @AuthenticationPrincipal HekmaPrincipal caller,
            @Parameter(description = "Whether to filter only patients assigned directly to caller (SPONSOR/SITE)")
            @RequestParam(value = "assignedToMe", defaultValue = "false") Boolean assignedToMe,
            @Parameter(description = "Optional tenant filter (for ADMIN or SYSTEM_ADMIN)")
            @RequestParam(value = "tenantId", required = false) UUID filterTenantId,
            @Parameter(description = "Page number (0-indexed)")
            @RequestParam(value = "page", defaultValue = "0") int page,
            @Parameter(description = "Page size")
            @RequestParam(value = "size", defaultValue = "20") int size) {
        Page<PatientResponse> responses = patientService.listPatients(
                caller.userId(),
                assignedToMe,
                filterTenantId,
                PageRequest.of(page, size, Sort.by("createdAt").descending())
        );
        return ResponseEntity.ok(com.hekma.identity.dto.PagedResponse.of(responses));
    }

    @GetMapping("/{patientId}")
    @Operation(
            summary = "Get patient profile details by user ID",
            description = "Retrieves patient clinical details. Enforces tenant boundaries for SPONSOR and SITE callers."
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "Patient profile found",
                    content = @Content(schema = @Schema(implementation = PatientResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "Cross-tenant access forbidden",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "Patient not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    @PreAuthorize("hasRole('PATIENT') or hasAuthority('patient:read')")
    public ResponseEntity<PatientResponse> getPatientById(
            @Parameter(description = "UUID of patient user", required = true)
            @PathVariable("patientId") UUID patientId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        PatientResponse response = patientService.getPatientById(patientId, caller.userId());
        return ResponseEntity.ok(response);
    }

    @PatchMapping("/{patientId}")
    @Operation(
            summary = "Update a patient's profile",
            description = "Updates first name, last name and phone number. Allowed for the patient itself, platform administrators, " +
                    "and SPONSOR/SITE users holding patient:update whose subtree contains the patient. Others receive 404."
    )
    @PreAuthorize("hasRole('PATIENT') or hasAuthority('patient:update')")
    public ResponseEntity<PatientResponse> updatePatient(
            @Parameter(description = "UUID of patient user", required = true)
            @PathVariable("patientId") UUID patientId,
            @Valid @org.springframework.web.bind.annotation.RequestBody com.hekma.identity.dto.patient.PatientUpdateRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(patientService.updatePatient(patientId, request, caller));
    }

    @PatchMapping("/{patientId}/assign")
    @Operation(
            summary = "Assign or reassign a patient to an investigator",
            description = "Reassigns a patient to another SITE or SPONSOR investigator within the same tenant. " +
                    "Platform administrators can also assign unassigned default-tenant patients to a clinical site coordinator."
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "Patient successfully assigned",
                    content = @Content(schema = @Schema(implementation = PatientResponse.class))
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Invalid target investigator or validation failure",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "Cross-tenant assignment forbidden",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "Patient or investigator not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    @PreAuthorize("hasAuthority('patient:assign')")
    public ResponseEntity<PatientResponse> assignPatient(
            @Parameter(description = "UUID of patient user", required = true)
            @PathVariable("patientId") UUID patientId,
            @Valid @org.springframework.web.bind.annotation.RequestBody PatientAssignRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        PatientResponse response = patientService.assignPatient(patientId, request, caller.userId());
        return ResponseEntity.ok(response);
    }
}
