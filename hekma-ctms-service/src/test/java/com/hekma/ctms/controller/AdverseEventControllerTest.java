package com.hekma.ctms.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.ctms.dto.AdverseEventRequest;
import com.hekma.ctms.dto.StudyRequest;
import com.hekma.ctms.dto.StudySiteRequest;
import com.hekma.ctms.security.client.IdentityServiceClient;
import com.hekma.ctms.security.client.TokenIntrospectResponse;
import com.hekma.ctms.service.StudyService;
import com.hekma.ctms.service.StudySiteService;
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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Transactional
class AdverseEventControllerTest {

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private StudyService studyService;

    @Autowired
    private StudySiteService studySiteService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @MockitoBean
    private IdentityServiceClient identityServiceClient;

    private MockMvc mockMvc;

    private static final String TOKEN = "valid-token-ae";
    private final UUID userId = UUID.randomUUID();
    private final UUID tenantId = UUID.randomUUID();
    private final String tenantPath = "/sponsor-gamma/";

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();

        Mockito.when(identityServiceClient.introspect(eq(TOKEN))).thenReturn(
                new TokenIntrospectResponse(
                        true,
                        userId,
                        "cra@gamma.com",
                        "SPONSOR",
                        tenantId,
                        tenantPath,
                        Set.of("study:read", "study:create", "site:manage", "adverse_event:create", "adverse_event:read", "adverse_event:update", "adverse_event:delete"),
                        Set.of("Clinical Research Associate")
                )
        );
    }

    @Test
    @DisplayName("Log, retrieve and update Adverse Event")
    void logAndManageAdverseEvent_success() throws Exception {
        var principal = new com.hekma.ctms.security.CtmsPrincipal(userId, "cra@gamma.com", "SPONSOR", tenantId, tenantPath, Set.of("study:create", "site:manage"), Set.of());

        // 1. Create study & site
        var studyRes = studyService.createStudy(
                StudyRequest.builder().studyNumber("STD-AE-01").studyTitle("AE Protocol").status("ACTIVE").build(),
                principal
        );
        String studyId = studyRes.getStudyId();

        studySiteService.addStudySite(
                StudySiteRequest.builder().studyId(studyId).siteId("SITE-AE-1").siteName("AE Site").status("ACTIVE").build(),
                principal
        );

        // 2. Log adverse event
        AdverseEventRequest aeReq = AdverseEventRequest.builder()
                .patientId("PAT-5501")
                .aeTerm("Grade 2 Rash")
                .severity("MODERATE")
                .causality("PROBABLE")
                .outcome("RECOVERING")
                .startDate("2026-10-10")
                .summary("Patient developed mild rash after drug administration")
                .build();

        String createAeRes = mockMvc.perform(post("/api/v1/studies/" + studyId + "/sites/SITE-AE-1/adverse-events")
                        .header("Authorization", "Bearer " + TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(aeReq)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.adverseEventId", notNullValue()))
                .andExpect(jsonPath("$.data.aeTerm", is("Grade 2 Rash")))
                .andExpect(jsonPath("$.data.severity", is("MODERATE")))
                .andReturn().getResponse().getContentAsString();

        String aeId = objectMapper.readTree(createAeRes).get("data").get("adverseEventId").asText();

        // 3. Get adverse event by ID
        mockMvc.perform(get("/api/v1/studies/adverse-events/" + aeId)
                        .header("Authorization", "Bearer " + TOKEN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.adverseEventId", is(aeId)))
                .andExpect(jsonPath("$.data.patientId", is("PAT-5501")));

        // 4. Update adverse event
        AdverseEventRequest updateReq = AdverseEventRequest.builder()
                .patientId("PAT-5501")
                .aeTerm("Grade 2 Rash (Resolved)")
                .severity("MILD")
                .outcome("RESOLVED")
                .build();

        mockMvc.perform(put("/api/v1/studies/adverse-events/" + aeId)
                        .header("Authorization", "Bearer " + TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(updateReq)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.aeTerm", is("Grade 2 Rash (Resolved)")))
                .andExpect(jsonPath("$.data.outcome", is("RESOLVED")));
    }
}
