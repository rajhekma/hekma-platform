package com.hekma.identity.controller;

import com.hekma.identity.dto.ApiErrorResponse;
import com.hekma.identity.dto.role.CreateCustomRoleRequest;
import com.hekma.identity.dto.role.CustomRoleResponse;
import com.hekma.identity.dto.role.UpdateCustomRoleRequest;
import com.hekma.identity.security.HekmaPrincipal;
import com.hekma.identity.service.CustomRoleService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/custom-roles")
@Tag(name = "Custom Role Governance", description = "Endpoints for defining, modifying, deleting, and listing custom functional roles")
public class CustomRoleController {

    private final CustomRoleService customRoleService;

    public CustomRoleController(CustomRoleService customRoleService) {
        this.customRoleService = customRoleService;
    }

    @PostMapping
    @Operation(
            summary = "Create a new custom role",
            description = "Defines a custom functional role bundling granular authorities. Enforces Grant <= Own (the creator " +
                    "cannot bundle authorities they do not hold). Platform administrators can create global roles or tenant roles; " +
                    "tenant staff can only create roles within their tenant subtree."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Custom role successfully created",
                    content = @Content(schema = @Schema(implementation = CustomRoleResponse.class))),
            @ApiResponse(responseCode = "400", description = "Validation failure or duplicate role code",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "403", description = "Insufficient authority or attempted grant beyond own permissions",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('role:create')")
    public ResponseEntity<CustomRoleResponse> createCustomRole(
            @Valid @RequestBody CreateCustomRoleRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        CustomRoleResponse response = customRoleService.createCustomRole(request, caller);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    @Operation(
            summary = "List visible custom roles",
            description = "Lists all custom roles visible to the caller (global template roles plus roles in the caller's tenant subtree). " +
                    "Optionally filtered by tenant ID."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "List of visible custom roles",
                    content = @Content(schema = @Schema(implementation = CustomRoleResponse.class))),
            @ApiResponse(responseCode = "403", description = "Insufficient authority or tenant filter outside scope",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('role:read')")
    public ResponseEntity<List<CustomRoleResponse>> listCustomRoles(
            @Parameter(description = "Optional filter by tenant UUID")
            @RequestParam(name = "tenantId", required = false) UUID tenantId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        List<CustomRoleResponse> responses = customRoleService.listCustomRoles(tenantId, caller);
        return ResponseEntity.ok(responses);
    }

    @GetMapping("/{roleId}")
    @Operation(
            summary = "Get custom role details",
            description = "Retrieves full configuration and authority bundle for a single custom role by ID."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Custom role details",
                    content = @Content(schema = @Schema(implementation = CustomRoleResponse.class))),
            @ApiResponse(responseCode = "403", description = "Role is outside caller's visibility scope",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "Custom role not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('role:read')")
    public ResponseEntity<CustomRoleResponse> getCustomRole(
            @Parameter(description = "UUID of custom role to fetch", required = true)
            @PathVariable("roleId") UUID roleId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        CustomRoleResponse response = customRoleService.getCustomRole(roleId, caller);
        return ResponseEntity.ok(response);
    }

    @PutMapping("/{roleId}")
    @Operation(
            summary = "Update an existing custom role",
            description = "Updates the name, description, active state, or authority bundle of a custom role. " +
                    "Immutable system roles cannot be modified. Enforces Grant <= Own on any new authorities."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Custom role updated successfully",
                    content = @Content(schema = @Schema(implementation = CustomRoleResponse.class))),
            @ApiResponse(responseCode = "400", description = "Validation failure or invalid authority",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "403", description = "Role outside scope, system role modification, or authority elevation attempt",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "Custom role not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('role:update')")
    public ResponseEntity<CustomRoleResponse> updateCustomRole(
            @Parameter(description = "UUID of custom role to update", required = true)
            @PathVariable("roleId") UUID roleId,
            @Valid @RequestBody UpdateCustomRoleRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        CustomRoleResponse response = customRoleService.updateCustomRole(roleId, request, caller);
        return ResponseEntity.ok(response);
    }

    @DeleteMapping("/{roleId}")
    @Operation(
            summary = "Soft-delete a custom role",
            description = "Soft-deletes a custom role. Rejects deletion if any active users are currently assigned to this role."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "Custom role successfully deleted"),
            @ApiResponse(responseCode = "400", description = "Role has active assigned users and cannot be deleted",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "403", description = "Insufficient authority or attempted deletion of a system role",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "Custom role not found",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('role:delete')")
    public ResponseEntity<Void> deleteCustomRole(
            @Parameter(description = "UUID of custom role to delete", required = true)
            @PathVariable("roleId") UUID roleId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        customRoleService.deleteCustomRole(roleId, caller);
        return ResponseEntity.noContent().build();
    }
}
