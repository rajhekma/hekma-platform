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
import static org.hamcrest.Matchers.notNullValue;
import static org.mockito.ArgumentMatchers.eq;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Transactional
class StudyControllerTest {

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private ObjectMapper objectMapper;

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
    @DisplayName("Reject unauthenticated access to /api/v1/studies (401)")
    void unauthenticatedRequest_returns401() throws Exception {
        mockMvc.perform(get("/api/v1/studies"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status", is(401)));
    }

    @Test
    @DisplayName("Create and retrieve clinical study with valid bearer token")
    void createAndGetStudy_success() throws Exception {
        String testToken = "valid-token-sponsor";
        UUID sponsorUserId = UUID.randomUUID();
        UUID tenantId = UUID.randomUUID();
        String tenantPath = "/sponsor-alpha/";

        Mockito.when(identityServiceClient.introspect(eq(testToken))).thenReturn(
                new TokenIntrospectResponse(
                        true,
                        sponsorUserId,
                        "sponsor.admin@alpha.com",
                        "SPONSOR",
                        tenantId,
                        tenantPath,
                        Set.of("study:create", "study:read", "study:update"),
                        Set.of("Sponsor Admin")
                )
        );

        StudyRequest request = StudyRequest.builder()
                .studyNumber("STD-2026-ALPHA")
                .studyTitle("Phase III Randomized Study on Compound X")
                .devPhase("Phase III")
                .status("ACTIVE")
                .therapeuticArea("Cardiology")
                .build();

        // 1. Create Study
        String createResponse = mockMvc.perform(post("/api/v1/studies")
                        .header("Authorization", "Bearer " + testToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.studyId", notNullValue()))
                .andExpect(jsonPath("$.data.studyTitle", is("Phase III Randomized Study on Compound X")))
                .andReturn().getResponse().getContentAsString();

        String studyId = objectMapper.readTree(createResponse).get("data").get("studyId").asText();

        // 2. Retrieve Study by ID
        mockMvc.perform(get("/api/v1/studies/" + studyId)
                        .header("Authorization", "Bearer " + testToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.studyNumber", is("STD-2026-ALPHA")));

        // 3. List Studies
        mockMvc.perform(get("/api/v1/studies")
                        .header("Authorization", "Bearer " + testToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.length()", is(1)));
    }
}
