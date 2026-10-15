package com.hekma.appointment.security.client;

import java.util.Set;
import java.util.UUID;

public record TokenIntrospectResponse(
        boolean active,
        UUID userId,
        String email,
        String role,
        UUID tenantId,
        String tenantPath,
        Set<String> authorities,
        Set<String> customRoles
) {
    public static TokenIntrospectResponse inactive() {
        return new TokenIntrospectResponse(false, null, null, null, null, null, Set.of(), Set.of());
    }
}
