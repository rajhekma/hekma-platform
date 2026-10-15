package com.hekma.identity.service;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserQueryServiceTest {

    @Mock
    private UserRepository userRepository;

    @Mock
    private PatientDetailRepository patientDetailRepository;

    @InjectMocks
    private UserQueryService userQueryService;

    private UserEntity sysAdmin;
    private UserEntity adminUser;
    private UserEntity sponsorUser;
    private UserEntity siteUser;
    private UserEntity patientUser;
    private PatientDetailEntity patientDetail;

    @BeforeEach
    void setUp() {
        sysAdmin = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-sysadmin")
                .email("system.admin@hekma.com")
                .role(Role.SYSTEM_ADMIN)
                .displayName("System Administrator")
                .status(UserStatus.ACTIVE)
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();

        adminUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-admin")
                .email("admin@hekma.com")
                .role(Role.ADMIN)
                .displayName("Trial Admin")
                .status(UserStatus.ACTIVE)
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();

        sponsorUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-sponsor")
                .email("sponsor@pharma.com")
                .role(Role.SPONSOR)
                .displayName("Pharma Sponsor")
                .status(UserStatus.ACTIVE)
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();

        siteUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-site")
                .email("site@hospital.org")
                .role(Role.SITE)
                .displayName("Site PI")
                .status(UserStatus.ACTIVE)
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();

        patientUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .firebaseUid("fb-patient")
                .email("patient@example.com")
                .role(Role.PATIENT)
                .displayName("Alice Patient")
                .status(UserStatus.ACTIVE)
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();

        patientDetail = PatientDetailEntity.builder()
                .id(UUID.randomUUID())
                .user(patientUser)
                .firstName("Alice")
                .lastName("Patient")
                .phoneNumber("+1234567890")
                .invitationCode("SITE-INVITE-01")
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .consentedAt(Instant.now())
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();
    }

    @Test
    @DisplayName("getUsers with null role returns all users across platform")
    void getUsers_nullRole_returnsAllUsers() {
        when(userRepository.findAllByOrderByCreatedAtDesc())
                .thenReturn(List.of(sysAdmin, adminUser, sponsorUser, siteUser, patientUser));

        List<UserEntity> result = userQueryService.getUsers(null);

        assertThat(result).hasSize(5);
        assertThat(result).extracting(UserEntity::getRole)
                .containsExactly(Role.SYSTEM_ADMIN, Role.ADMIN, Role.SPONSOR, Role.SITE, Role.PATIENT);
        verify(userRepository).findAllByOrderByCreatedAtDesc();
    }

    @Test
    @DisplayName("getUsers with ADMIN role returns only admin users")
    void getUsers_adminRole_returnsFilteredUsers() {
        when(userRepository.findByRoleOrderByCreatedAtDesc(Role.ADMIN))
                .thenReturn(List.of(adminUser));

        List<UserEntity> result = userQueryService.getUsers(Role.ADMIN);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getRole()).isEqualTo(Role.ADMIN);
        assertThat(result.get(0).getEmail()).isEqualTo("admin@hekma.com");
        verify(userRepository).findByRoleOrderByCreatedAtDesc(Role.ADMIN);
    }

    @Test
    @DisplayName("getUserById returns user when found")
    void getUserById_existingId_returnsUser() {
        UUID id = adminUser.getId();
        when(userRepository.findById(id)).thenReturn(Optional.of(adminUser));

        Optional<UserEntity> result = userQueryService.getUserById(id);

        assertThat(result).isPresent();
        assertThat(result.get().getEmail()).isEqualTo("admin@hekma.com");
    }

    @Test
    @DisplayName("getUserByEmail returns user when found with case-insensitive trim")
    void getUserByEmail_existingEmail_returnsUser() {
        when(userRepository.findByEmail("admin@hekma.com")).thenReturn(Optional.of(adminUser));

        Optional<UserEntity> result = userQueryService.getUserByEmail("  ADMIN@HEKMA.COM  ");

        assertThat(result).isPresent();
        assertThat(result.get().getEmail()).isEqualTo("admin@hekma.com");
    }

    @Test
    @DisplayName("getUserCount returns total count when role is null")
    void getUserCount_nullRole_returnsTotalCount() {
        when(userRepository.count()).thenReturn(10L);

        long count = userQueryService.getUserCount(null);

        assertThat(count).isEqualTo(10L);
    }

    @Test
    @DisplayName("getUserCount with role returns count for that role")
    void getUserCount_withRole_returnsRoleCount() {
        when(userRepository.countByRole(Role.PATIENT)).thenReturn(4L);

        long count = userQueryService.getUserCount(Role.PATIENT);

        assertThat(count).isEqualTo(4L);
    }

    @Test
    @DisplayName("getPatientDetailsForUsers batch loads details for patient users")
    void getPatientDetailsForUsers_resolvesPatientDetails() {
        when(patientDetailRepository.findByUserIn(List.of(patientUser)))
                .thenReturn(List.of(patientDetail));

        Map<UserEntity, PatientDetailEntity> map = userQueryService.getPatientDetailsForUsers(List.of(adminUser, patientUser));

        assertThat(map).hasSize(1);
        assertThat(map.get(patientUser)).isEqualTo(patientDetail);
    }

    @Test
    @DisplayName("getPatientDetailForUser returns detail for patient user")
    void getPatientDetailForUser_patientUser_returnsDetail() {
        when(patientDetailRepository.findByUser(patientUser)).thenReturn(Optional.of(patientDetail));

        Optional<PatientDetailEntity> result = userQueryService.getPatientDetailForUser(patientUser);

        assertThat(result).isPresent();
        assertThat(result.get().getFirstName()).isEqualTo("Alice");
    }

    @Test
    @DisplayName("getPatientDetailForUser returns empty for non-patient user")
    void getPatientDetailForUser_nonPatientUser_returnsEmpty() {
        Optional<PatientDetailEntity> result = userQueryService.getPatientDetailForUser(adminUser);

        assertThat(result).isEmpty();
    }
}
