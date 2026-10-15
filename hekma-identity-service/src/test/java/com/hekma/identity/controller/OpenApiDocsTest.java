package com.hekma.identity.controller;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class OpenApiDocsTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext).build();
    }

    @Test
    @DisplayName("GET /v3/api-docs returns 200 OK with all endpoints and schemas documented")
    void openApiDocs_returnsCompleteSpecification() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.info.title").value("Hekma Identity Service API"))
                .andExpect(jsonPath("$.paths['/api/v1/auth/register']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/register'].post.tags[0]").value("Authentication"))
                .andExpect(jsonPath("$.paths['/api/v1/auth/patient/register']").doesNotExist())
                .andExpect(jsonPath("$.paths['/api/v1/auth/login']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/login'].post.tags[0]").value("Authentication"))
                .andExpect(jsonPath("$.paths['/api/v1/auth/refresh-token']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/refresh-token'].post.tags[0]").value("Authentication"))
                .andExpect(jsonPath("$.paths['/api/v1/auth/otp/send']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/otp/send'].post.tags[0]").value("Authentication"))
                .andExpect(jsonPath("$.paths['/api/v1/auth/otp/resend']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/otp/resend'].post.tags[0]").value("Authentication"))
                .andExpect(jsonPath("$.paths['/api/v1/auth/otp/verify']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/otp/verify'].post.tags[0]").value("Authentication"))
                .andExpect(jsonPath("$.paths['/api/v1/system-admin/invite-admin']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/invite-admin']").doesNotExist())
                .andExpect(jsonPath("$.components.schemas['RegisterRequest']").exists())
                .andExpect(jsonPath("$.components.schemas['LoginRequest']").exists())
                .andExpect(jsonPath("$.components.schemas['LoginResponse']").exists())
                .andExpect(jsonPath("$.components.schemas['InviteAdminRequest']").exists())
                .andExpect(jsonPath("$.components.schemas['SendOtpRequest']").exists())
                .andExpect(jsonPath("$.components.schemas['VerifyOtpRequest']").exists())
                .andExpect(jsonPath("$.components.schemas['VerifyOtpResponse']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/users/{userId}/status']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/users/{userId}/2fa']").exists())
                .andExpect(jsonPath("$.paths['/api/v1/users/{userId}']").exists())
                .andExpect(jsonPath("$.components.schemas['UpdateUserStatusRequest']").exists())
                .andExpect(jsonPath("$.components.schemas['UpdateTwoFactorRequest']").exists())
                .andExpect(jsonPath("$.components.schemas['UserResponse']").exists())
                .andExpect(jsonPath("$.components.schemas['ApiErrorResponse']").exists());
    }
}
