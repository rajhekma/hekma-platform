package com.hekma.ctms.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.ctms.domain.StudyEntity;
import com.hekma.ctms.domain.StudySiteEntity;
import com.hekma.ctms.dto.CmtsWebhookPayload;
import com.hekma.ctms.repository.StudyRepository;
import com.hekma.ctms.repository.StudySiteRepository;
import com.hekma.ctms.security.client.IdentityServiceClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.util.Map;

import static org.hamcrest.Matchers.is;
import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Transactional
class CmtsWebhookControllerTest {

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private StudyRepository studyRepository;

    @Autowired
    private StudySiteRepository studySiteRepository;

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
    @DisplayName("Generate keys and process EDC adverse event webhook")
    void generateKeysAndProcessWebhook() throws Exception {
        // 1. Generate keys for Study 101 and Site 202
        String keyResponseStr = mockMvc.perform(post("/webhook/cmts/generate-keys")
                        .param("studyId", "101")
                        .param("siteId", "202"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.accessKey", notNullValue()))
                .andExpect(jsonPath("$.data.secretKey", notNullValue()))
                .andReturn().getResponse().getContentAsString();

        Map<?, ?> responseMap = objectMapper.readValue(keyResponseStr, Map.class);
        Map<?, ?> data = (Map<?, ?>) responseMap.get("data");
        String accessKey = (String) data.get("accessKey");
        String secretKey = (String) data.get("secretKey");

        // 2. Reject request with invalid secret key (401)
        CmtsWebhookPayload payload = CmtsWebhookPayload.builder()
                .resourceType("ADVERSE_EVENTS")
                .studyId("101")
                .siteId("202")
                .patientId("PAT-001")
                .data(Map.of(
                        "aeTerm", "Headache",
                        "severity", "MILD",
                        "startDate", "2026-10-12"
                ))
                .build();

        mockMvc.perform(post("/webhook/cmts")
                        .header("X-Access-Key", accessKey)
                        .header("X-Secret-Key", "invalid-secret")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code", is(401)));

        // 3. Reject request with mismatched studyId scope (403)
        CmtsWebhookPayload wrongScopePayload = CmtsWebhookPayload.builder()
                .resourceType("ADVERSE_EVENTS")
                .studyId("999")
                .siteId("202")
                .patientId("PAT-001")
                .data(Map.of("aeTerm", "Headache"))
                .build();

        mockMvc.perform(post("/webhook/cmts")
                        .header("X-Access-Key", accessKey)
                        .header("X-Secret-Key", secretKey)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(wrongScopePayload)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code", is(403)));

        // 4. Ingest adverse event successfully with valid keys (200)
        mockMvc.perform(post("/webhook/cmts")
                        .header("X-Access-Key", accessKey)
                        .header("X-Secret-Key", secretKey)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data", notNullValue()));
    }

    @Test
    @DisplayName("Load data via EDC webhook read endpoint")
    void loadDataViaWebhook() throws Exception {
        // Setup study and site
        studyRepository.save(StudyEntity.builder()
                .studyId("STD-101")
                .studyNumber("STD-101")
                .studyTitle("Oncology Phase II Study")
                .status("ACTIVE")
                .build());

        studySiteRepository.save(StudySiteEntity.builder()
                .studyId("STD-101")
                .siteId("SITE-202")
                .siteName("Memorial Sloan Kettering")
                .status("ACTIVE")
                .build());

        // Generate keys
        String keyResponseStr = mockMvc.perform(post("/webhook/cmts/generate-keys")
                        .param("studyId", "STD-101")
                        .param("siteId", "SITE-202"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Map<?, ?> responseMap = objectMapper.readValue(keyResponseStr, Map.class);
        Map<?, ?> data = (Map<?, ?>) responseMap.get("data");
        String accessKey = (String) data.get("accessKey");
        String secretKey = (String) data.get("secretKey");

        // Read study site data
        mockMvc.perform(get("/api/v1/webhook/cmts/load_data")
                        .header("X-Access-Key", accessKey)
                        .header("X-Secret-Key", secretKey)
                        .param("resourceType", "STUDY_SITE"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code", is(200)))
                .andExpect(jsonPath("$.data.siteName", is("Memorial Sloan Kettering")));
    }
}
