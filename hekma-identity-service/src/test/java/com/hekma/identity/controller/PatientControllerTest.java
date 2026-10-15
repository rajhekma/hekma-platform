package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.dto.patient.PatientAcceptInviteRequest;
import com.hekma.identity.dto.patient.PatientAssignRequest;
import com.hekma.identity.dto.patient.PatientInviteRequest;
import com.hekma.identity.dto.patient.PatientInviteResponse;
import com.hekma.identity.dto.patient.PatientResponse;
import com.hekma.identity.exception.GlobalExceptionHandler;
import com.hekma.identity.support.TestAuthentication;
import com.hekma.identity.exception.InvalidInvitationException;
import com.hekma.identity.service.PatientService;
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

import java.util.List;
import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class PatientControllerTest {

    private MockMvc mockMvc;

    @Mock
    private PatientService patientService;

    @InjectMocks
    private PatientController patientController;

    private ObjectMapper objectMapper;
    private UUID patientId;
    private UUID callerId;

    @AfterEach
    void tearDown() {
        TestAuthentication.clear();
    }

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(patientController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new AuthenticationPrincipalArgumentResolver())
                .build();

        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());

        patientId = UUID.randomUUID();
        callerId = UUID.randomUUID();
        TestAuthentication.authenticate(callerId, Role.SITE, UUID.randomUUID());
    }

    @Test
    @DisplayName("POST /api/v1/patients/invite returns 201 Created on valid request")
    void invitePatient_valid_returns201() throws Exception {
        PatientInviteRequest request = PatientInviteRequest.builder()
                .firstName("Jane")
                .lastName("Doe")
                .email("jane.doe@example.com")
                .phoneNumber("+15551234567")
                .build();

        PatientInviteResponse response = PatientInviteResponse.builder()
                .patientId(patientId)
                .email("jane.doe@example.com")
                .invitationCode("INV-TEST-001")
                .tenantId(UUID.randomUUID())
                .assignedUserId(callerId)
                .message("Patient invited successfully.")
                .build();

        when(patientService.invitePatient(any(PatientInviteRequest.class), any())).thenReturn(response);

        mockMvc.perform(post("/api/v1/patients/invite")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email").value("jane.doe@example.com"))
                .andExpect(jsonPath("$.invitationCode").value("INV-TEST-001"));
    }

    @Test
    @DisplayName("POST /api/v1/patients/invite returns 400 Bad Request on invalid email")
    void invitePatient_invalidEmail_returns400() throws Exception {
        PatientInviteRequest request = PatientInviteRequest.builder()
                .firstName("Jane")
                .lastName("Doe")
                .email("not-an-email")
                .build();

        mockMvc.perform(post("/api/v1/patients/invite")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Validation failed for input data"));
    }

    @Test
    @DisplayName("POST /api/v1/patients/accept-invite returns 200 OK on valid token and consents")
    void acceptInvite_valid_returns200() throws Exception {
        PatientAcceptInviteRequest request = PatientAcceptInviteRequest.builder()
                .invitationToken("INV-TEST-001")
                .password("SecurePass123!")
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .build();

        PatientResponse response = PatientResponse.builder()
                .id(patientId)
                .email("jane.doe@example.com")
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .termsAccepted(true)
                .message("Patient invitation accepted successfully.")
                .build();

        when(patientService.acceptInvite(any(PatientAcceptInviteRequest.class))).thenReturn(response);

        mockMvc.perform(post("/api/v1/patients/accept-invite")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("jane.doe@example.com"))
                .andExpect(jsonPath("$.status").value("ACTIVE"))
                .andExpect(jsonPath("$.isActive").value(true));
    }

    @Test
    @DisplayName("POST /api/v1/patients/accept-invite returns 400 Bad Request when token is invalid")
    void acceptInvite_invalidToken_returns400() throws Exception {
        PatientAcceptInviteRequest request = PatientAcceptInviteRequest.builder()
                .invitationToken("INVALID-TOKEN")
                .password("SecurePass123!")
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .build();

        when(patientService.acceptInvite(any(PatientAcceptInviteRequest.class)))
                .thenThrow(new InvalidInvitationException("Invalid or expired invitation code/token."));

        mockMvc.perform(post("/api/v1/patients/accept-invite")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message", containsString("Invalid or expired")));
    }

    @Test
    @DisplayName("GET /api/v1/patients returns 200 OK with paginated list")
    void listPatients_returns200() throws Exception {
        PatientResponse patient = PatientResponse.builder()
                .id(patientId)
                .email("jane.doe@example.com")
                .status(UserStatus.ACTIVE)
                .build();

        when(patientService.listPatients(any(), any(), any(), any(Pageable.class)))
                .thenReturn(new PageImpl<>(List.of(patient)));

        mockMvc.perform(get("/api/v1/patients"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].email").value("jane.doe@example.com"));
    }

    @Test
    @DisplayName("GET /api/v1/patients/{patientId} returns 200 OK when found")
    void getPatientById_returns200() throws Exception {
        PatientResponse response = PatientResponse.builder()
                .id(patientId)
                .email("jane.doe@example.com")
                .status(UserStatus.ACTIVE)
                .build();

        when(patientService.getPatientById(eq(patientId), any())).thenReturn(response);

        mockMvc.perform(get("/api/v1/patients/{patientId}", patientId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(patientId.toString()))
                .andExpect(jsonPath("$.email").value("jane.doe@example.com"));
    }

    @Test
    @DisplayName("PATCH /api/v1/patients/{patientId}/assign returns 200 OK on reassign")
    void assignPatient_returns200() throws Exception {
        UUID newAssigneeId = UUID.randomUUID();
        PatientAssignRequest request = PatientAssignRequest.builder()
                .assignedUserId(newAssigneeId)
                .build();

        PatientResponse response = PatientResponse.builder()
                .id(patientId)
                .email("jane.doe@example.com")
                .assignedUserId(newAssigneeId)
                .assignedUserName("Dr. Smith")
                .build();

        when(patientService.assignPatient(eq(patientId), any(PatientAssignRequest.class), any())).thenReturn(response);

        mockMvc.perform(patch("/api/v1/patients/{patientId}/assign", patientId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.assignedUserId").value(newAssigneeId.toString()))
                .andExpect(jsonPath("$.assignedUserName").value("Dr. Smith"));
    }
}
