package com.hekma.ctms.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.ctms.dto.StudyRequest;
import com.hekma.ctms.dto.StudySiteRequest;
import com.hekma.ctms.repository.StudyRepository;
import com.hekma.ctms.security.client.IdentityServiceClient;
import com.hekma.ctms.security.client.TokenIntrospectResponse;
import com.hekma.ctms.service.StudyService;
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
class StudySiteControllerTest {

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private StudyService studyService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @MockitoBean
    private IdentityServiceClient identityServiceClient;

    private MockMvc mockMvc;

    private static final String TOKEN = "valid-token-site-admin";
    private final UUID sponsorUserId = UUID.randomUUID();
    private final UUID tenantId = UUID.randomUUID();
    private final String tenantPath = "/sponsor-beta/";

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();

        Mockito.when(identityServiceClient.introspect(eq(TOKEN))).thenReturn(
                new TokenIntrospectResponse(
                        true,
                        sponsorUserId,
                        "site.manager@beta.com",
                        "SPONSOR",
                        tenantId,
                        tenantPath,
                        Set.of("study:read", "study:create", "site:manage", "query:read", "query:create"),
                        Set.of("Study Site Manager")
                )
        );
    }

    @Test
    @DisplayName("Allocate site to study and retrieve sites")
    void addAndGetStudySite_success() throws Exception {
        // 1. Create a study first
        var studyRes = studyService.createStudy(
                StudyRequest.builder()
                        .studyNumber("STD-SITE-01")
                        .studyTitle("Site Allocation Testing Protocol")
                        .status("ACTIVE")
                        .build(),
                new com.hekma.ctms.security.CtmsPrincipal(sponsorUserId, "site.manager@beta.com", "SPONSOR", tenantId, tenantPath, Set.of("study:create"), Set.of())
        );
        String studyId = studyRes.getStudyId();

        // 2. Add site
        StudySiteRequest siteReq = StudySiteRequest.builder()
                .siteId("SITE-101")
                .siteName("Central Hospital Research Center")
                .status("ACTIVE")
                .onboardStatus("INITIATED")
                .role("INVESTIGATOR_SITE")
                .primaryContact("Dr. Smith")
                .build();

        mockMvc.perform(post("/api/v1/studies/" + studyId + "/sites")
                        .header("Authorization", "Bearer " + TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(siteReq)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.siteId", is("SITE-101")))
                .andExpect(jsonPath("$.data.siteName", is("Central Hospital Research Center")));

        // 3. Get study sites
        mockMvc.perform(get("/api/v1/studies/" + studyId + "/sites")
                        .header("Authorization", "Bearer " + TOKEN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.length()", is(1)))
                .andExpect(jsonPath("$.data[0].siteId", is("SITE-101")));
    }
}
