package com.hekma.identity.controller;

import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.dto.ApiErrorResponse;
import com.hekma.identity.dto.tenant.SubTenantCreateRequest;
import com.hekma.identity.dto.tenant.TenantResponse;
import com.hekma.identity.dto.tenant.TenantStatusUpdateRequest;
import com.hekma.identity.dto.tenant.TenantUpdateRequest;
import com.hekma.identity.security.HekmaPrincipal;
import com.hekma.identity.service.TenantService;
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
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

/**
 * Tenant hierarchy management. Top-level tenants are created only through {@code POST /api/v1/auth/register-tenant}.
 * Platform administrators manage every tenant (they hold every authority); SPONSOR/SITE users act within their own
 * tenant's subtree according to their authorities (tenant:read, tenant:update, subtenant:create, subtenant:manage).
 */
@RestController
@RequestMapping("/api/v1/tenants")
@Tag(name = "Tenant Management", description = "Endpoints for governing and querying the tenant hierarchy")
public class TenantController {

    private final TenantService tenantService;

    public TenantController(TenantService tenantService) {
        this.tenantService = tenantService;
    }

    @PostMapping("/{tenantId}/sub-tenants")
    @Operation(
            summary = "Create a sub-tenant",
            description = "Creates a SPONSOR or SITE sub-tenant under a tenant in the caller's scope (any type, any depth), " +
                    "optionally with its first user whose role equals the sub-tenant's type. Not allowed under the default tenant."
    )
    @RequestBody(
            description = "Sub-tenant creation payload",
            required = true,
            content = @Content(
                    schema = @Schema(implementation = SubTenantCreateRequest.class),
                    examples = @ExampleObject(
                            name = "Site under a sponsor",
                            value = "{\n  \"name\": \"Mayo Clinic Rochester Site\",\n  \"slug\": \"mayo-rochester\",\n  \"tenantType\": \"SITE\",\n  \"owner\": {\n    \"email\": \"coordinator@mayo.edu\",\n    \"displayName\": \"Dr. Emily Watson\",\n    \"temporaryPassword\": \"TempPassword123!\"\n  }\n}"
                    )
            )
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Sub-tenant created",
                    content = @Content(schema = @Schema(implementation = TenantResponse.class))),
            @ApiResponse(responseCode = "400", description = "Validation error or slug already exists",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "403", description = "Parent is the default tenant or not active",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "Parent tenant not found in the caller's scope",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "409", description = "Owner email or phone already registered",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('subtenant:create')")
    public ResponseEntity<TenantResponse> createSubTenant(
            @Parameter(description = "UUID of the parent tenant", required = true)
            @PathVariable("tenantId") UUID tenantId,
            @Valid @org.springframework.web.bind.annotation.RequestBody SubTenantCreateRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        TenantResponse response = tenantService.createSubTenant(tenantId, request, caller);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    @Operation(
            summary = "List tenant organizations in scope",
            description = "Returns a paginated list of tenants, optionally filtered by type and status. Platform administrators " +
                    "see every tenant; SPONSOR/SITE users see their own tenant and all of its descendants."
    )
    @PreAuthorize("hasAuthority('tenant:read')")
    public ResponseEntity<com.hekma.identity.dto.PagedResponse<TenantResponse>> listTenants(
            @Parameter(description = "Filter by tenant type (SPONSOR, SITE, GENERAL)")
            @RequestParam(value = "type", required = false) TenantType type,
            @Parameter(description = "Filter by status (PENDING_VERIFICATION, ACTIVE, SUSPENDED, INACTIVE)")
            @RequestParam(value = "status", required = false) TenantStatus status,
            @Parameter(description = "Page number (0-indexed)")
            @RequestParam(value = "page", defaultValue = "0") int page,
            @Parameter(description = "Page size")
            @RequestParam(value = "size", defaultValue = "20") int size,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        Page<TenantResponse> responses = tenantService.listTenants(type, status,
                PageRequest.of(page, size, Sort.by("createdAt").descending()), caller);
        return ResponseEntity.ok(com.hekma.identity.dto.PagedResponse.of(responses));
    }

    @GetMapping("/{tenantId}")
    @Operation(
            summary = "Get tenant organization by ID",
            description = "Retrieves tenant details, hierarchy position and member count. Out-of-scope tenants return 404."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Tenant found",
                    content = @Content(schema = @Schema(implementation = TenantResponse.class))),
            @ApiResponse(responseCode = "404", description = "Tenant not found in the caller's scope",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<TenantResponse> getTenantById(
            @Parameter(description = "UUID of the tenant organization", required = true)
            @PathVariable("tenantId") UUID tenantId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(tenantService.getTenantById(tenantId, caller));
    }

    @GetMapping("/{tenantId}/children")
    @Operation(
            summary = "List direct sub-tenants",
            description = "Returns the direct children of a tenant in the caller's scope."
    )
    @PreAuthorize("hasAuthority('tenant:read')")
    public ResponseEntity<List<TenantResponse>> getChildren(
            @Parameter(description = "UUID of the parent tenant", required = true)
            @PathVariable("tenantId") UUID tenantId,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(tenantService.getChildren(tenantId, caller));
    }

    @GetMapping("/slug/{slug}")
    @Operation(
            summary = "Get tenant organization by slug",
            description = "Retrieves tenant details and metadata by URL slug (platform administrators)."
    )
    @PreAuthorize("hasAnyRole('SYSTEM_ADMIN', 'ADMIN')")
    public ResponseEntity<TenantResponse> getTenantBySlug(
            @Parameter(description = "Slug of the tenant organization", required = true)
            @PathVariable("slug") String slug) {
        return ResponseEntity.ok(tenantService.getTenantBySlug(slug));
    }

    @PatchMapping("/{tenantId}/status")
    @Operation(
            summary = "Update tenant operational status",
            description = "Sets ACTIVE, SUSPENDED or INACTIVE. A non-active tenant blocks access for its whole subtree. " +
                    "Tenant users can change only strict descendants of their own tenant; the default tenant cannot be suspended."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Tenant status updated",
                    content = @Content(schema = @Schema(implementation = TenantResponse.class))),
            @ApiResponse(responseCode = "403", description = "Own tenant, or default tenant suspension",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "Tenant not found in the caller's scope",
                    content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    @PreAuthorize("hasAuthority('subtenant:manage')")
    public ResponseEntity<TenantResponse> updateTenantStatus(
            @Parameter(description = "UUID of tenant to update", required = true)
            @PathVariable("tenantId") UUID tenantId,
            @Valid @org.springframework.web.bind.annotation.RequestBody TenantStatusUpdateRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(tenantService.updateTenantStatus(tenantId, request, caller));
    }

    @PutMapping("/{tenantId}")
    @Operation(
            summary = "Update tenant metadata and settings",
            description = "Modifies organization profile, contacts and settings of a tenant in the caller's scope."
    )
    @PreAuthorize("hasAuthority('tenant:update')")
    public ResponseEntity<TenantResponse> updateTenant(
            @Parameter(description = "UUID of tenant to update", required = true)
            @PathVariable("tenantId") UUID tenantId,
            @Valid @org.springframework.web.bind.annotation.RequestBody TenantUpdateRequest request,
            @AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(tenantService.updateTenant(tenantId, request, caller));
    }
}
