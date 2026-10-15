package com.hekma.identity.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.support.TestAuthentication;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
class UserGraphQlControllerIntegrationTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private PatientDetailRepository patientDetailRepository;

    @Autowired
    private EntityManager entityManager;

    @Autowired
    private org.springframework.transaction.support.TransactionTemplate transactionTemplate;

    private MockMvc mockMvc;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private UserEntity adminUser;
    private UserEntity sponsorUser;
    private UserEntity siteUser;
    private UserEntity patientUser;
    private PatientDetailEntity patientDetail;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
                .apply(SecurityMockMvcConfigurers.springSecurity())
                .build();

        transactionTemplate.executeWithoutResult(status -> {
            patientDetailRepository.deleteAll();
            entityManager.createNativeQuery("DELETE FROM identity_users WHERE role != 'SYSTEM_ADMIN'").executeUpdate();
            entityManager.flush();
            entityManager.clear();
        });

        adminUser = userRepository.save(UserEntity.builder()
                .firebaseUid("fb-admin-" + UUID.randomUUID())
                .email("admin.gql@hekma.com")
                .role(Role.ADMIN)
                .displayName("GQL Admin")
                .status(UserStatus.ACTIVE)
                .build());

        sponsorUser = userRepository.save(UserEntity.builder()
                .firebaseUid("fb-sponsor-" + UUID.randomUUID())
                .email("sponsor.gql@hekma.com")
                .role(Role.SPONSOR)
                .displayName("GQL Sponsor")
                .status(UserStatus.ACTIVE)
                .build());

        siteUser = userRepository.save(UserEntity.builder()
                .firebaseUid("fb-site-" + UUID.randomUUID())
                .email("site.gql@hekma.com")
                .role(Role.SITE)
                .displayName("GQL Site")
                .status(UserStatus.ACTIVE)
                .build());

        patientUser = userRepository.save(UserEntity.builder()
                .firebaseUid("fb-patient-" + UUID.randomUUID())
                .email("patient.gql@hekma.com")
                .role(Role.PATIENT)
                .displayName("GQL Patient")
                .status(UserStatus.ACTIVE)
                .build());

        patientDetail = patientDetailRepository.save(PatientDetailEntity.builder()
                .user(patientUser)
                .firstName("John")
                .lastName("Patient")
                .phoneNumber("+15551234567")
                .invitationCode("SITE-INVITE-42")
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .consentedAt(Instant.now())
                .build());
    }

    @Test
    @DisplayName("GraphQL query: users without role returns all types of users on platform")
    void queryUsers_withoutRoleFilter_returnsAllUsers() throws Exception {
        String query = "query { users { id email role displayName status } }";
        Map<String, String> payload = Map.of("query", query);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.users", hasSize(greaterThanOrEqualTo(5))))
                .andExpect(jsonPath("$.data.users[*].role", hasItems("SYSTEM_ADMIN", "ADMIN", "SPONSOR", "SITE", "PATIENT")));
    }

    @Test
    @DisplayName("GraphQL query: users with role filter returns only matching role")
    void queryUsers_withRoleFilter_returnsOnlyFilteredUsers() throws Exception {
        String query = "query { users(role: ADMIN) { id email role displayName } }";
        Map<String, String> payload = Map.of("query", query);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.users", hasSize(greaterThanOrEqualTo(1))))
                .andExpect(jsonPath("$.data.users[*].role", everyItem(is("ADMIN"))));
    }

    @Test
    @DisplayName("GraphQL query: users with PATIENT role resolves nested patientDetails")
    void queryUsers_patientRole_resolvesPatientDetails() throws Exception {
        String query = """
                query {
                    users(role: PATIENT) {
                        id
                        email
                        role
                        patientDetails {
                            firstName
                            lastName
                            phoneNumber
                            invitationCode
                            termsAccepted
                            privacyPolicyAccepted
                            healthDataConsentAccepted
                        }
                    }
                }
                """;
        Map<String, String> payload = Map.of("query", query);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.users", hasSize(greaterThanOrEqualTo(1))))
                .andExpect(jsonPath("$.data.users[?(@.email == 'patient.gql@hekma.com')].patientDetails.firstName").value(hasItem("John")))
                .andExpect(jsonPath("$.data.users[?(@.email == 'patient.gql@hekma.com')].patientDetails.invitationCode").value(hasItem("SITE-INVITE-42")))
                .andExpect(jsonPath("$.data.users[?(@.email == 'patient.gql@hekma.com')].patientDetails.termsAccepted").value(hasItem(true)));
    }

    @Test
    @DisplayName("GraphQL query: userById returns matching user")
    void queryUserById_existingId_returnsUser() throws Exception {
        String query = String.format("query { userById(id: \"%s\") { id email role } }", adminUser.getId());
        Map<String, String> payload = Map.of("query", query);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.userById.id").value(adminUser.getId().toString()))
                .andExpect(jsonPath("$.data.userById.email").value("admin.gql@hekma.com"))
                .andExpect(jsonPath("$.data.userById.role").value("ADMIN"));
    }

    @Test
    @DisplayName("GraphQL query: userByEmail returns matching user")
    void queryUserByEmail_existingEmail_returnsUser() throws Exception {
        String query = "query { userByEmail(email: \"sponsor.gql@hekma.com\") { id email role } }";
        Map<String, String> payload = Map.of("query", query);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.userByEmail.email").value("sponsor.gql@hekma.com"))
                .andExpect(jsonPath("$.data.userByEmail.role").value("SPONSOR"));
    }

    @Test
    @DisplayName("GraphQL query: userCount returns total and filtered counts")
    void queryUserCount_returnsCounts() throws Exception {
        String query = """
                query {
                    totalUsers: userCount
                    patientCount: userCount(role: PATIENT)
                    sponsorCount: userCount(role: SPONSOR)
                }
                """;
        Map<String, String> payload = Map.of("query", query);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.totalUsers").value(greaterThanOrEqualTo(5)))
                .andExpect(jsonPath("$.data.patientCount").value(greaterThanOrEqualTo(1)))
                .andExpect(jsonPath("$.data.sponsorCount").value(greaterThanOrEqualTo(1)));
    }

    @Test
    @DisplayName("GraphQL query: userById returns isActive and isDeleted fields")
    void queryUserById_returnsActiveAndDeletedFlags() throws Exception {
        String query = String.format("""
                query {
                    userById(id: "%s") {
                        id
                        email
                        isActive
                        isDeleted
                        status
                    }
                }
                """, patientUser.getId());
        Map<String, String> payload = Map.of("query", query);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.userById.id").value(patientUser.getId().toString()))
                .andExpect(jsonPath("$.data.userById.isActive").value(true))
                .andExpect(jsonPath("$.data.userById.isDeleted").value(false));
    }

    @Test
    @DisplayName("GraphQL mutation: updateUserActiveStatus updates user status")
    void mutation_updateUserActiveStatus() throws Exception {
        String mutation = String.format("""
                mutation {
                    updateUserActiveStatus(userId: "%s", isActive: false) {
                        id
                        isActive
                        status
                    }
                }
                """, patientUser.getId());
        Map<String, String> payload = Map.of("query", mutation);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.updateUserActiveStatus.isActive").value(false))
                .andExpect(jsonPath("$.data.updateUserActiveStatus.status").value("INACTIVE"));
    }

    @Test
    @DisplayName("GraphQL mutation: softDeleteUser soft-deletes user and removes from subsequent queries")
    void mutation_softDeleteUser() throws Exception {
        String mutation = String.format("""
                mutation {
                    softDeleteUser(userId: "%s")
                }
                """, patientUser.getId());
        Map<String, String> payload = Map.of("query", mutation);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.softDeleteUser").value(true));

        // Verify subsequent userById returns null due to @SQLRestriction
        String query = String.format("""
                query {
                    userById(id: "%s") {
                        id
                    }
                }
                """, patientUser.getId());
        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("query", query))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.userById").doesNotExist());
    }

    @Test
    @DisplayName("GraphQL mutation: updateUserTwoFactor updates twoFactorEnabled flag")
    void mutation_updateUserTwoFactor() throws Exception {
        String mutation = String.format("""
                mutation {
                    updateUserTwoFactor(userId: "%s", twoFactorEnabled: true) {
                        id
                        twoFactorEnabled
                    }
                }
                """, patientUser.getId());
        Map<String, String> payload = Map.of("query", mutation);

        mockMvc.perform(post("/graphql")
                        .header("Authorization", TestAuthentication.bearer(adminUser))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errors").doesNotExist())
                .andExpect(jsonPath("$.data.updateUserTwoFactor.id").value(patientUser.getId().toString()))
                .andExpect(jsonPath("$.data.updateUserTwoFactor.twoFactorEnabled").value(true));
    }
}
