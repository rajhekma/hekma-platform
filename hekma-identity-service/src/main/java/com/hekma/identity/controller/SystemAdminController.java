package com.hekma.identity.controller;

import com.hekma.identity.dto.ApiErrorResponse;
import com.hekma.identity.dto.InviteAdminRequest;
import com.hekma.identity.dto.RegisterResponse;
import com.hekma.identity.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import com.hekma.identity.security.HekmaPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.dto.iam.AuthorityDefinitionResponse;
import com.hekma.identity.dto.iam.RoleAuthoritiesResponse;
import com.hekma.identity.dto.iam.UpdateRoleAuthoritiesRequest;
import com.hekma.identity.service.RoleAuthorityService;
import com.hekma.identity.service.StaffInvitationService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import java.util.List;
import java.util.Set;

@RestController
@RequestMapping("/api/v1/system-admin")
@Tag(name = "System Administration", description = "Administrative operations strictly reserved for the SYSTEM_ADMIN")
public class SystemAdminController {

    private final AuthService authService;
    private final RoleAuthorityService roleAuthorityService;

    public SystemAdminController(AuthService authService, RoleAuthorityService roleAuthorityService) {
        this.authService = authService;
        this.roleAuthorityService = roleAuthorityService;
    }

    @PostMapping({"/admins", "/invite-admin"})
    @PreAuthorize("hasRole('SYSTEM_ADMIN')")
    @Operation(
            summary = "Invite or create an ADMIN user",
            description = "Creates an ADMIN user in Firebase Auth with custom claim `role: ADMIN` and saves the profile in PostgreSQL. " +
                    "This endpoint is exclusively used by the `SYSTEM_ADMIN` to onboard additional administrators to the platform."
    )
    @RequestBody(
            description = "Admin user creation payload with email, temporary password, and display name",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = InviteAdminRequest.class),
                    examples = @ExampleObject(
                            name = "Admin Invitation Example",
                            summary = "Create an ADMIN user",
                            value = "{\n  \"email\": \"new.admin@hekma.com\",\n  \"temporaryPassword\": \"AdminTempPass123!\",\n  \"displayName\": \"Clinical Trial Coordinator\"\n}"
                    )
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "201",
                    description = "Admin user successfully created in Firebase Auth and PostgreSQL",
                    content = @Content(
                            schema = @Schema(implementation = RegisterResponse.class),
                            examples = @ExampleObject(
                                    name = "Success Response",
                                    value = "{\n  \"id\": \"b9281a02-5e4c-47bc-9177-3e4e94119d50\",\n  \"firebaseUid\": \"fb-admin-778899\",\n  \"email\": \"new.admin@hekma.com\",\n  \"role\": \"ADMIN\",\n  \"displayName\": \"Clinical Trial Coordinator\",\n  \"status\": \"ACTIVE\",\n  \"createdAt\": \"2026-09-28T12:00:00Z\",\n  \"message\": \"Admin user invited successfully.\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Validation error on input data (invalid email or temporary password too short)",
                    content = @Content(
                            schema = @Schema(implementation = ApiErrorResponse.class),
                            examples = @ExampleObject(
                                    name = "Validation Error",
                                    value = "{\n  \"status\": 400,\n  \"error\": \"Bad Request\",\n  \"message\": \"Validation failed for input data\",\n  \"details\": [\"temporaryPassword: Password must be at least 8 characters long\"],\n  \"timestamp\": \"2026-09-28T12:00:00Z\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "409",
                    description = "Email is already registered in the system or Firebase",
                    content = @Content(
                            schema = @Schema(implementation = ApiErrorResponse.class),
                            examples = @ExampleObject(
                                    name = "Duplicate Email Error",
                                    value = "{\n  \"status\": 409,\n  \"error\": \"Conflict\",\n  \"message\": \"A user with email 'new.admin@hekma.com' is already registered in the system.\",\n  \"timestamp\": \"2026-09-28T12:00:00Z\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "502",
                    description = "Firebase service communication error",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    public ResponseEntity<RegisterResponse> inviteAdmin(@Valid @org.springframework.web.bind.annotation.RequestBody InviteAdminRequest request,
                                                        @AuthenticationPrincipal HekmaPrincipal caller) {
        RegisterResponse response = authService.inviteAdmin(request, caller != null ? caller.userId() : null);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/authorities")
    @PreAuthorize("hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get platform authority catalogue",
            description = "Returns all platform authorities with category groupings and descriptions.")
    public ResponseEntity<List<AuthorityDefinitionResponse>> getAuthorities() {
        return ResponseEntity.ok(roleAuthorityService.getAuthorityCatalogue());
    }

    @GetMapping("/roles/authorities")
    @PreAuthorize("hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get all configurable role default authorities",
            description = "Returns default authorities configured for ADMIN, SPONSOR, and SITE.")
    public ResponseEntity<List<RoleAuthoritiesResponse>> getAllRoleAuthorities() {
        return ResponseEntity.ok(roleAuthorityService.getAllRoleAuthorities());
    }

    @GetMapping("/roles/{role}/authorities")
    @PreAuthorize("hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Get default authorities for a specific role",
            description = "Returns default authorities configured for the specified role (ADMIN, SPONSOR, SITE).")
    public ResponseEntity<RoleAuthoritiesResponse> getRoleAuthorities(@PathVariable("role") Role role) {
        return ResponseEntity.ok(roleAuthorityService.getRoleAuthoritiesResponse(role));
    }

    @PutMapping("/roles/{role}/authorities")
    @PreAuthorize("hasRole('SYSTEM_ADMIN')")
    @Operation(summary = "Configure default authorities for a platform role",
            description = "Assigns or removes default authorities for configurable roles (ADMIN, SPONSOR, SITE). "
                    + "If applyToExistingUsers is true, cascades changes to all active existing users of that role.")
    public ResponseEntity<RoleAuthoritiesResponse> updateRoleAuthorities(
            @PathVariable("role") Role role,
            @Valid @org.springframework.web.bind.annotation.RequestBody UpdateRoleAuthoritiesRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        Set<Authority> wanted = StaffInvitationService.parseStrict(request.getAuthorities());
        RoleAuthoritiesResponse response = roleAuthorityService.updateRoleAuthorities(
                role,
                wanted,
                Boolean.TRUE.equals(request.getApplyToExistingUsers()),
                request.getReason(),
                caller
        );
        return ResponseEntity.ok(response);
    }
}
