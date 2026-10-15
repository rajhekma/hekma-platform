package com.hekma.identity.controller;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.dto.iam.AuthoritiesResponse;
import com.hekma.identity.dto.iam.MeResponse;
import com.hekma.identity.security.HekmaPrincipal;
import com.hekma.identity.service.UserManagementService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The authenticated caller's own identity, tenant position and effective authorities. Clients render their UI
 * from this data; the server still enforces every rule.
 */
@RestController
@RequestMapping("/api/v1/me")
@Tag(name = "Me", description = "The authenticated caller's profile, tenant and authorities")
public class MeController {

    private final UserManagementService userManagementService;

    public MeController(UserManagementService userManagementService) {
        this.userManagementService = userManagementService;
    }

    @GetMapping
    @Operation(summary = "Get the caller's profile", description = "Profile, role, tenant (with path) and effective authority keys.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<MeResponse> me(@AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(userManagementService.me(caller));
    }

    @GetMapping("/authorities")
    @Operation(summary = "Get the caller's effective authorities",
            description = "All authorities for platform administrators, the granted set for SPONSOR/SITE users, none for patients.")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<AuthoritiesResponse> myAuthorities(@AuthenticationPrincipal HekmaPrincipal caller) {
        return ResponseEntity.ok(AuthoritiesResponse.builder()
                .userId(caller.userId())
                .authorities(caller.authorities().stream().map(Authority::key).sorted().toList())
                .build());
    }
}
