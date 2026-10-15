package com.hekma.ctms.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.ctms.dto.StudyRequest;
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

import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static org.hamcrest.Matchers.is;
import static org.hamcrest.Matchers.notNullValue;
import static org.mockito.ArgumentMatchers.eq;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Transactional
class StudyGraphQlControllerTest {

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private StudyService studyService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @MockitoBean
    private IdentityServiceClient identityServiceClient;

    private MockMvc mockMvc;

    private static final String TOKEN = "valid-token-gql";
    private final UUID userId = UUID.randomUUID();
    private final UUID tenantId = UUID.randomUUID();
    private final String tenantPath = "/sponsor-gql/";

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();

        Mockito.when(identityServiceClient.introspect(eq(TOKEN))).thenReturn(
                new TokenIntrospectResponse(
                        true,
                        userId,
                        "gql.user@sponsor.com",
                        "SPONSOR",
                        tenantId,
                        tenantPath,
                        Set.of("study:read", "study:create", "study:update"),
                        Set.of("Clinical Investigator")
                )
        );
    }

    @Test
    @DisplayName("Execute GraphQL Mutation createStudy and Query getStudy")
    void graphQl_createAndGetStudy_success() throws Exception {
        // 1. Mutation: createStudy
        String mutation = """
                mutation {
                    createStudy(studyNumber: "STD-GQL-100", studyTitle: "GraphQL Oncology Trial", devPhase: "Phase II", status: "ACTIVE") {
                        code
                        message
                        data
                    }
                }
                """;

        String mutationPayload = objectMapper.writeValueAsString(Map.of("query", mutation));

        String mutationResponse = mockMvc.perform(post("/graphql")
                        .header("Authorization", "Bearer " + TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(mutationPayload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.createStudy.code", is(200)))
                .andExpect(jsonPath("$.data.createStudy.data", notNullValue()))
                .andReturn().getResponse().getContentAsString();

        String studyId = objectMapper.readTree(mutationResponse).get("data").get("createStudy").get("data").asText();

        // 2. Query: getStudy
        String query = String.format("""
                query {
                    getStudy(studyId: "%s") {
                        studyId
                        studyNumber
                        studyTitle
                        status
                    }
                }
                """, studyId);

        String queryPayload = objectMapper.writeValueAsString(Map.of("query", query));

        mockMvc.perform(post("/graphql")
                        .header("Authorization", "Bearer " + TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(queryPayload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.getStudy.studyId", is(studyId)))
                .andExpect(jsonPath("$.data.getStudy.studyNumber", is("STD-GQL-100")))
                .andExpect(jsonPath("$.data.getStudy.studyTitle", is("GraphQL Oncology Trial")));
    }
}
