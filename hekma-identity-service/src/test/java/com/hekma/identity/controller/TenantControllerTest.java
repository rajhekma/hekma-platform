package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.dto.tenant.SubTenantCreateRequest;
import com.hekma.identity.dto.tenant.TenantOwnerRequest;
import com.hekma.identity.dto.tenant.TenantResponse;
import com.hekma.identity.dto.tenant.TenantStatusUpdateRequest;
import com.hekma.identity.dto.tenant.TenantUpdateRequest;
import com.hekma.identity.exception.GlobalExceptionHandler;
import com.hekma.identity.support.TestAuthentication;
import com.hekma.identity.exception.TenantNotFoundException;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.service.TenantService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.http.MediaType;
import org.springframework.security.web.method.annotation.AuthenticationPrincipalArgumentResolver;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class TenantControllerTest {

    private MockMvc mockMvc;

    @Mock
    private TenantService tenantService;

    @InjectMocks
    private TenantController tenantController;

    private ObjectMapper objectMapper;
    private UUID tenantId;

    @AfterEach
    void tearDown() {
        TestAuthentication.clear();
    }

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(tenantController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new AuthenticationPrincipalArgumentResolver())
                .build();

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
        tenantId = UUID.randomUUID();
        TestAuthentication.authenticate(UUID.randomUUID(), Role.SYSTEM_ADMIN, null);
    }

    @Test
    @DisplayName("POST /api/v1/tenants/{tenantId}/sub-tenants returns 201 Created on valid input")
    void createSubTenant_valid_returns201() throws Exception {
        SubTenantCreateRequest request = SubTenantCreateRequest.builder()
                .name("Mayo Clinic Rochester Site")
                .slug("mayo-rochester")
                .tenantType(TenantType.SITE)
                .build();

        UUID childId = UUID.randomUUID();
        TenantResponse response = TenantResponse.builder()
                .id(childId)
                .name("Mayo Clinic Rochester Site")
                .slug("mayo-rochester")
                .tenantType(TenantType.SITE)
                .parentTenantId(tenantId)
                .depth(1)
                .status(TenantStatus.ACTIVE)
                .createdAt(Instant.now())
                .message("Sub-tenant organization created successfully.")
                .build();

        when(tenantService.createSubTenant(eq(tenantId), any(SubTenantCreateRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/tenants/{tenantId}/sub-tenants", tenantId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.slug").value("mayo-rochester"))
                .andExpect(jsonPath("$.parentTenantId").value(tenantId.toString()))
                .andExpect(jsonPath("$.depth").value(1));
    }

    @Test
    @DisplayName("POST /api/v1/tenants/{tenantId}/sub-tenants returns 400 Bad Request on invalid slug format")
    void createSubTenant_invalidSlug_returns400() throws Exception {
        SubTenantCreateRequest request = SubTenantCreateRequest.builder()
                .name("Invalid Slug Clinic")
                .slug("Invalid Slug!")
                .tenantType(TenantType.SITE)
                .build();

        mockMvc.perform(post("/api/v1/tenants/{tenantId}/sub-tenants", tenantId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("POST /api/v1/tenants/{tenantId}/sub-tenants rejects an owner with a weak temporary password")
    void createSubTenant_weakOwnerPassword_returns400() throws Exception {
        SubTenantCreateRequest request = SubTenantCreateRequest.builder()
                .name("Mayo Clinic Rochester Site")
                .slug("mayo-rochester")
                .tenantType(TenantType.SITE)
                .owner(TenantOwnerRequest.builder().email("owner@mayo.edu").temporaryPassword("weak").build())
                .build();

        mockMvc.perform(post("/api/v1/tenants/{tenantId}/sub-tenants", tenantId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("GET /api/v1/tenants/{tenantId}/children returns the direct sub-tenants")
    void getChildren_returns200() throws Exception {
        when(tenantService.getChildren(eq(tenantId), any())).thenReturn(List.of(
                TenantResponse.builder().id(UUID.randomUUID()).slug("child-a").parentTenantId(tenantId).depth(1).build()));

        mockMvc.perform(get("/api/v1/tenants/{tenantId}/children", tenantId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].slug").value("child-a"));
    }

    @Test
    @DisplayName("GET /api/v1/tenants returns 200 OK with paginated list")
    void listTenants_returns200() throws Exception {
        TenantResponse tenant = TenantResponse.builder()
                .id(tenantId)
                .name("Default Organization")
                .slug("default-tenant")
                .defaultTenant(true)
                .status(TenantStatus.ACTIVE)
                .build();

        when(tenantService.listTenants(any(), any(), any(Pageable.class), any()))
                .thenReturn(new PageImpl<>(List.of(tenant)));

        mockMvc.perform(get("/api/v1/tenants"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].slug").value("default-tenant"));
    }

    @Test
    @DisplayName("GET /api/v1/tenants/{tenantId} returns 200 OK when found")
    void getTenantById_found_returns200() throws Exception {
        TenantResponse response = TenantResponse.builder()
                .id(tenantId)
                .name("Pfizer")
                .slug("pfizer")
                .status(TenantStatus.ACTIVE)
                .build();

        when(tenantService.getTenantById(eq(tenantId), any())).thenReturn(response);

        mockMvc.perform(get("/api/v1/tenants/{tenantId}", tenantId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(tenantId.toString()))
                .andExpect(jsonPath("$.name").value("Pfizer"));
    }

    @Test
    @DisplayName("GET /api/v1/tenants/{tenantId} returns 404 Not Found when absent")
    void getTenantById_notFound_returns404() throws Exception {
        when(tenantService.getTenantById(eq(tenantId), any()))
                .thenThrow(new TenantNotFoundException("Tenant not found with ID: " + tenantId));

        mockMvc.perform(get("/api/v1/tenants/{tenantId}", tenantId))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message", containsString("Tenant not found")));
    }

    @Test
    @DisplayName("PATCH /api/v1/tenants/{tenantId}/status returns 403 Forbidden when default tenant is targeted")
    void updateTenantStatus_forbiddenForDefaultTenant() throws Exception {
        TenantStatusUpdateRequest request = TenantStatusUpdateRequest.builder()
                .status(TenantStatus.SUSPENDED)
                .reason("Test")
                .build();

        when(tenantService.updateTenantStatus(eq(tenantId), any(TenantStatusUpdateRequest.class), any()))
                .thenThrow(new UnauthorizedOperationException("Default platform organization cannot be suspended or deactivated."));

        mockMvc.perform(patch("/api/v1/tenants/{tenantId}/status", tenantId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.message", containsString("cannot be suspended or deactivated")));
    }

    @Test
    @DisplayName("PUT /api/v1/tenants/{tenantId} returns 200 OK on update")
    void updateTenant_returns200() throws Exception {
        TenantUpdateRequest request = TenantUpdateRequest.builder()
                .name("Pfizer Global")
                .build();

        TenantResponse response = TenantResponse.builder()
                .id(tenantId)
                .name("Pfizer Global")
                .status(TenantStatus.ACTIVE)
                .build();

        when(tenantService.updateTenant(eq(tenantId), any(TenantUpdateRequest.class), any())).thenReturn(response);

        mockMvc.perform(put("/api/v1/tenants/{tenantId}", tenantId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Pfizer Global"));
    }
}
