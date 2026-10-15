package com.hekma.ctms.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.ctms.dto.StudyRequest;
import com.hekma.ctms.security.client.IdentityServiceClient;
import com.hekma.ctms.security.client.TokenIntrospectResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.util.Set;
import java.util.UUID;

import static org.hamcrest.Matchers.is;
import static org.mockito.ArgumentMatchers.eq;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Transactional
class SecurityAuthorizationTest {

    @Autowired
    private WebApplicationContext context;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @MockitoBean
    private IdentityServiceClient identityServiceClient;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();
    }

    @Test
    @DisplayName("Request with missing Bearer token returns 401")
    void missingToken_returns401() throws Exception {
        mockMvc.perform(get("/api/v1/studies"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status", is(401)))
                .andExpect(jsonPath("$.error", is("Unauthorized")));
    }

    @Test
    @DisplayName("Request with inactive or expired token returns 401")
    void inactiveToken_returns401() throws Exception {
        String token = "invalid-or-expired-token";
        Mockito.when(identityServiceClient.introspect(eq(token))).thenReturn(
                new TokenIntrospectResponse(false, null, null, null, null, null, Set.of(), Set.of())
        );

        mockMvc.perform(get("/api/v1/studies")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status", is(401)));
    }

    @Test
    @DisplayName("Principal lacking required authority is forbidden (403)")
    void missingAuthority_returns403() throws Exception {
        String token = "read-only-user-token";
        Mockito.when(identityServiceClient.introspect(eq(token))).thenReturn(
                new TokenIntrospectResponse(
                        true,
                        UUID.randomUUID(),
                        "viewer@site.com",
                        "SITE",
                        UUID.randomUUID(),
                        "/site-1/",
                        Set.of("study:read"), // Has read, but NOT study:create
                        Set.of("Viewer")
                )
        );

        StudyRequest request = StudyRequest.builder()
                .studyNumber("FORBIDDEN-TEST")
                .studyTitle("Unauthorized creation attempt")
                .build();

        mockMvc.perform(post("/api/v1/studies")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status", is(403)))
                .andExpect(jsonPath("$.error", is("Forbidden")));
    }
}
