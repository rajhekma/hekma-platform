package com.hekma.identity.controller;

import com.hekma.identity.dto.ApiErrorResponse;
import com.hekma.identity.dto.UpdateTwoFactorRequest;
import com.hekma.identity.dto.UpdateUserStatusRequest;
import com.hekma.identity.dto.UserResponse;
import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.dto.iam.AuthoritiesResponse;
import com.hekma.identity.dto.iam.StaffAcceptInviteRequest;
import com.hekma.identity.dto.iam.StaffInviteRequest;
import com.hekma.identity.dto.iam.StaffInviteResponse;
import com.hekma.identity.dto.iam.UpdateAuthoritiesRequest;
import com.hekma.identity.dto.role.AssignCustomRolesRequest;
import com.hekma.identity.dto.role.UserCustomRolesResponse;
import com.hekma.identity.security.HekmaPrincipal;
import com.hekma.identity.service.AuthorityService;
import com.hekma.identity.service.CustomRoleService;
import com.hekma.identity.service.StaffInvitationService;
import com.hekma.identity.service.UserManagementService;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestParam;
import java.util.Set;
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
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/users")
@Tag(name = "User Management", description = "Endpoints for managing user status, active/inactive state, and soft deletion")
public class UserController {

    private final UserManagementService userManagementService;
    private final AuthorityService authorityService;
    private final StaffInvitationService staffInvitationService;
    private final CustomRoleService customRoleService;

    public UserController(UserManagementService userManagementService,
                          AuthorityService authorityService,
                          StaffInvitationService staffInvitationService,
                          CustomRoleService customRoleService) {
        this.userManagementService = userManagementService;
        this.authorityService = authorityService;
        this.staffInvitationService = staffInvitationService;
        this.customRoleService = customRoleService;
    }

    @GetMapping
    @Operation(
            summary = "List users in scope",
            description = "Paged users, optionally filtered by role. Platform administrators see every user; SPONSOR/SITE users "
                    + "holding user:read see users of their tenant and its sub-tenants."
    )
    @PreAuthorize("hasAuthority('user:read')")
    public ResponseEntity<com.hekma.identity.dto.PagedResponse<UserResponse>> listUsers(
            @Parameter(description = "Filter by role") @RequestParam(value = "role", required = false) Role role,
            @Parameter(description = "Page number (0-indexed)") @RequestParam(value = "page", defaultValue = "0") int page,
            @Parameter(description = "Page size") @RequestParam(value = "size", defaultValue = "20") int size,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(com.hekma.identity.dto.PagedResponse.of(userManagementService.listUsers(role,
                PageRequest.of(page, size, Sort.by("createdAt").descending()), caller)));
    }

    @PostMapping("/invite")
    @Operation(
            summary = "Invite a SPONSOR/SITE user into a tenant",
            description = "Creates a single-use invitation (72 hours) into the caller's tenant or a sub-tenant. The role equals the "
                    + "tenant's type; granted authorities must be held by the inviter. The token is sent only by email."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Invitation created",
                    content = @Content(schema = @Schema(implementation = StaffInviteResponse.class))),
            @ApiResponse(responseCode = "403", description = "Requested authority not held by the inviter",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "Tenant not in the caller's scope",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "409", description = "Email already registered",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('user:invite')")
    public ResponseEntity<StaffInviteResponse> inviteStaff(
            @Valid @org.springframework.web.bind.annotation.RequestBody StaffInviteRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.status(HttpStatus.CREATED).body(staffInvitationService.invite(request, caller));
    }

    @PostMapping("/accept-invite")
    @Operation(
            summary = "Accept a staff invitation (public)",
            description = "Redeems a single-use invitation token, creates the account with the given password and grants the "
                    + "invitation's authorities. Expired or used tokens return 400."
    )
    public ResponseEntity<UserResponse> acceptStaffInvite(
            @Valid @org.springframework.web.bind.annotation.RequestBody StaffAcceptInviteRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(staffInvitationService.accept(request));
    }

    @GetMapping("/{userId}/authorities")
    @Operation(
            summary = "Get a user's authorities",
            description = "Visible to the user itself, platform administrators, and SPONSOR/SITE users holding user:read whose "
                    + "subtree contains the user. Others receive 404."
    )
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AuthoritiesResponse> getAuthorities(
            @PathVariable("userId") UUID userId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(toAuthoritiesResponse(userId, authorityService.getAuthorities(userId, caller)));
    }

    @PutMapping("/{userId}/authorities")
    @Operation(
            summary = "Replace a user's authorities",
            description = "Sets the complete authority list of a SPONSOR/SITE user in the caller's subtree. The caller can add or "
                    + "remove only authorities it holds itself and cannot change its own authorities. Audited."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Authorities replaced",
                    content = @Content(schema = @Schema(implementation = AuthoritiesResponse.class))),
            @ApiResponse(responseCode = "400", description = "Unknown authority key or target is not SPONSOR/SITE",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "403", description = "Self-change, or authority not held by the caller",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "User not in the caller's scope",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('authority:assign')")
    public ResponseEntity<AuthoritiesResponse> replaceAuthorities(
            @PathVariable("userId") UUID userId,
            @Valid @org.springframework.web.bind.annotation.RequestBody UpdateAuthoritiesRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        Set<Authority> wanted = StaffInvitationService.parseStrict(request.getAuthorities());
        return ResponseEntity.ok(toAuthoritiesResponse(userId,
                authorityService.replaceAuthorities(userId, wanted, request.getReason(), caller)));
    }

    private static AuthoritiesResponse toAuthoritiesResponse(UUID userId, Set<Authority> authorities) {
        return AuthoritiesResponse.builder()
                .userId(userId)
                .authorities(authorities.stream().map(Authority::key).sorted().toList())
                .build();
    }

    @PatchMapping("/{userId}/status")
    @Operation(
            summary = "Update user active/inactive status",
            description = "Modifies the active status of a target user, enforcing platform role hierarchy: " +
                    "<ul>" +
                    "<li><b>SYSTEM_ADMIN</b> can change active status of <b>ADMIN</b>, <b>SPONSOR</b>, <b>SITE</b>, and <b>PATIENT</b>.</li>" +
                    "<li><b>ADMIN</b> can change active status of users below them (<b>SPONSOR</b>, <b>SITE</b>, <b>PATIENT</b>).</li>" +
                    "<li><b>ADMIN</b> cannot modify another <b>ADMIN</b> or <b>SYSTEM_ADMIN</b>.</li>" +
                    "<li><b>SYSTEM_ADMIN</b> cannot be deactivated.</li>" +
                    "<li>Operational roles cannot modify user status.</li>" +
                    "</ul>"
    )
    @RequestBody(
            description = "User status update payload specifying new isActive flag",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = UpdateUserStatusRequest.class),
                    examples = {
                            @ExampleObject(
                                    name = "Deactivate User",
                                    summary = "Set user to inactive",
                                    value = "{\n  \"isActive\": false,\n  \"reason\": \"Compliance hold\"\n}"
                            ),
                            @ExampleObject(
                                    name = "Reactivate User",
                                    summary = "Set user to active",
                                    value = "{\n  \"isActive\": true,\n  \"reason\": \"Verification completed\"\n}"
                            )
                    }
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "User status successfully updated",
                    content = @Content(
                            schema = @Schema(implementation = UserResponse.class),
                            examples = @ExampleObject(
                                    name = "Status Update Success",
                                    value = "{\n  \"id\": \"7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6\",\n  \"firebaseUid\": \"fb-usr-987654321\",\n  \"email\": \"sponsor@pharma-corp.com\",\n  \"role\": \"SPONSOR\",\n  \"displayName\": \"Dr. Emily Watson\",\n  \"phoneNumber\": \"+1234567890\",\n  \"status\": \"INACTIVE\",\n  \"isActive\": false,\n  \"isDeleted\": false,\n  \"createdAt\": \"2026-09-28T12:00:00Z\",\n  \"updatedAt\": \"2026-09-30T14:00:00Z\",\n  \"message\": \"User status successfully updated to INACTIVE.\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Validation failure",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "Hierarchy violation or unauthorized operator role",
                    content = @Content(
                            schema = @Schema(implementation = ApiErrorResponse.class),
                            examples = @ExampleObject(
                                    name = "Hierarchy Violation",
                                    value = "{\n  \"status\": 403,\n  \"error\": \"Forbidden\",\n  \"message\": \"ADMIN users cannot modify the status of other ADMIN users. Only SYSTEM_ADMIN can modify an ADMIN user.\",\n  \"timestamp\": \"2026-09-30T14:00:00Z\"\n}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "Target user or operator user not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    @PreAuthorize("hasAuthority('user:manage')")
    public ResponseEntity<UserResponse> updateUserStatus(
            @Parameter(description = "UUID of target user whose status is being modified", required = true)
            @PathVariable("userId") UUID userId,
            @Valid @org.springframework.web.bind.annotation.RequestBody UpdateUserStatusRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        UserResponse response = userManagementService.updateUserStatus(userId, request, caller.userId());
        return ResponseEntity.ok(response);
    }

    @PatchMapping("/{userId}/2fa")
    @Operation(
            summary = "Enable or disable Two-Factor Authentication (2FA)",
            description = "Updates the two-factor authentication preference for a user (primarily for PATIENT profiles). " +
                    "When enabled, logging in triggers an OTP challenge before granting authentication tokens."
    )
    @RequestBody(
            description = "2FA preference payload",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = UpdateTwoFactorRequest.class),
                    examples = {
                            @ExampleObject(
                                    name = "Enable 2FA",
                                    summary = "Enable Two-Factor Authentication",
                                    value = "{\n  \"twoFactorEnabled\": true\n}"
                            ),
                            @ExampleObject(
                                    name = "Disable 2FA",
                                    summary = "Disable Two-Factor Authentication",
                                    value = "{\n  \"twoFactorEnabled\": false\n}"
                            )
                    }
            )
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "2FA preference successfully updated",
                    content = @Content(schema = @Schema(implementation = UserResponse.class))
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Validation failure",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "User account is inactive or suspended",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "User not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<UserResponse> updateTwoFactor(
            @Parameter(description = "UUID of user whose 2FA setting is being updated", required = true)
            @PathVariable("userId") UUID userId,
            @Valid @org.springframework.web.bind.annotation.RequestBody UpdateTwoFactorRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        UserResponse response = userManagementService.updateTwoFactor(userId, request.getTwoFactorEnabled(), caller);
        return ResponseEntity.ok(response);
    }

    @DeleteMapping("/{userId}")
    @Operation(
            summary = "Soft-delete a user",
            description = "Soft-deletes a user profile by setting `isDeleted = true`, `isActive = false`, and `status = INACTIVE`. " +
                    "Soft-deleted records are automatically filtered out from all queries via Hibernate `@SQLRestriction(\"is_deleted = false\")`. " +
                    "Follows the same administrative hierarchy as status modification."
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "User successfully soft-deleted",
                    content = @Content(schema = @Schema(implementation = UserResponse.class))
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Invalid request",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "403",
                    description = "Hierarchy violation (e.g. attempting to soft-delete SYSTEM_ADMIN or ADMIN modifying ADMIN)",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "Target user or operator not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    @PreAuthorize("hasAuthority('user:manage')")
    public ResponseEntity<UserResponse> softDeleteUser(
            @Parameter(description = "UUID of target user to soft-delete", required = true)
            @PathVariable("userId") UUID userId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        UserResponse response = userManagementService.softDeleteUser(userId, caller.userId());
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{userId}")
    @Operation(
            summary = "Get user profile by ID",
            description = "Retrieves active user profile details. Soft-deleted users return 404 Not Found."
    )
    @ApiResponses(value = {
            @ApiResponse(
                    responseCode = "200",
                    description = "User profile found",
                    content = @Content(schema = @Schema(implementation = UserResponse.class))
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "User not found or has been soft-deleted",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))
            )
    })
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<UserResponse> getUserById(
            @Parameter(description = "UUID of user to retrieve", required = true)
            @PathVariable("userId") UUID userId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        UserResponse response = userManagementService.getUserById(userId, caller);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{userId}/custom-roles")
    @Operation(
            summary = "Get a user's assigned custom roles and inherited authorities",
            description = "Retrieves all custom functional roles assigned to the user along with effective authorities aggregated from those roles."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "User custom roles retrieved",
                    content = @Content(schema = @Schema(implementation = UserCustomRolesResponse.class))),
            @ApiResponse(responseCode = "403", description = "Target user outside caller's tenant subtree",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "User not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('role:read')")
    public ResponseEntity<UserCustomRolesResponse> getUserCustomRoles(
            @Parameter(description = "UUID of target user", required = true)
            @PathVariable("userId") UUID userId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        UserCustomRolesResponse response = customRoleService.getUserCustomRoles(userId, caller);
        return ResponseEntity.ok(response);
    }

    @PutMapping("/{userId}/custom-roles")
    @Operation(
            summary = "Assign custom roles to a staff user",
            description = "Replaces the assigned custom roles of a staff user. Enforces No Self-Elevation, Grant <= Own (caller must hold all authorities bundled in assigned roles), and Subtree Isolation."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Custom roles successfully assigned",
                    content = @Content(schema = @Schema(implementation = UserCustomRolesResponse.class))),
            @ApiResponse(responseCode = "400", description = "Validation failure or role not applicable",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "403", description = "Self-elevation attempt, unheld authorities, or user outside subtree",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "User or custom role not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('role:assign')")
    public ResponseEntity<UserCustomRolesResponse> assignCustomRoles(
            @Parameter(description = "UUID of target user", required = true)
            @PathVariable("userId") UUID userId,
            @Valid @org.springframework.web.bind.annotation.RequestBody AssignCustomRolesRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        UserCustomRolesResponse response = customRoleService.assignCustomRoles(userId, request, caller);
        return ResponseEntity.ok(response);
    }
}
