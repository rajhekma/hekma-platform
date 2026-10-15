package com.hekma.identity.controller;

import com.hekma.identity.dto.iam.AuthorityDefinitionResponse;
import com.hekma.identity.service.RoleAuthorityService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Public/authenticated discovery endpoint for platform authority catalogue definitions and categories.
 */
@RestController
@RequestMapping("/api/v1/authorities")
@Tag(name = "Authorities", description = "Platform authority catalogue and permission definitions")
public class AuthorityController {

    private final RoleAuthorityService roleAuthorityService;

    public AuthorityController(RoleAuthorityService roleAuthorityService) {
        this.roleAuthorityService = roleAuthorityService;
    }

    @GetMapping
    @Operation(summary = "Get platform authority catalogue",
            description = "Returns all platform authorities categorized by functional groups.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<List<AuthorityDefinitionResponse>> getCatalogue() {
        return ResponseEntity.ok(roleAuthorityService.getAuthorityCatalogue());
    }
}
