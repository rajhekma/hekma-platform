package com.hekma.identity.service;

import com.hekma.identity.exception.UserNotFoundException;
import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.TenantEntity;
import com.hekma.identity.domain.TenantStatus;
import com.hekma.identity.domain.TenantType;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import com.hekma.identity.dto.patient.PatientAcceptInviteRequest;
import com.hekma.identity.dto.patient.PatientAssignRequest;
import com.hekma.identity.dto.patient.PatientInviteRequest;
import com.hekma.identity.dto.patient.PatientInviteResponse;
import com.hekma.identity.dto.patient.PatientResponse;
import com.hekma.identity.exception.InvalidInvitationException;
import com.hekma.identity.exception.TenantSuspendedException;
import com.hekma.identity.exception.UnauthorizedOperationException;
import com.hekma.identity.exception.UserAlreadyExistsException;
import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.firebase.FirebaseUserDto;
import com.hekma.identity.notification.NotificationServiceClient;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PatientServiceTest {

    @Mock
    private UserRepository userRepository;

    @Mock
    private AuditService auditService;

    @Mock
    private PatientDetailRepository patientDetailRepository;

    @Mock
    private TenantRepository tenantRepository;

    @Mock
    private FirebaseService firebaseService;

    @Mock
    private NotificationServiceClient notificationServiceClient;

    @InjectMocks
    private PatientService patientService;

    private TenantEntity siteTenant;
    private TenantEntity otherTenant;
    private UserEntity siteUser;
    private UserEntity anotherSiteUser;
    private UserEntity patientUser;
    private PatientDetailEntity patientDetail;

    @BeforeEach
    void setUp() {
        siteTenant = TenantEntity.builder()
                .id(UUID.randomUUID())
                .name("Mayo Clinic Site")
                .slug("mayo-clinic")
                .tenantType(TenantType.SITE)
                .status(TenantStatus.ACTIVE)
                .defaultTenant(false)
                .build();

        otherTenant = TenantEntity.builder()
                .id(UUID.randomUUID())
                .name("Roche Sponsor")
                .slug("roche")
                .tenantType(TenantType.SPONSOR)
                .status(TenantStatus.ACTIVE)
                .defaultTenant(false)
                .build();
        siteTenant.setPath("/" + siteTenant.getId() + "/");
        otherTenant.setPath("/" + otherTenant.getId() + "/");

        siteUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("investigator@mayo.edu")
                .displayName("Dr. Alice Smith")
                .role(Role.SITE)
                .tenant(siteTenant)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .build();

        anotherSiteUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("coordinator@mayo.edu")
                .displayName("Bob Coordinator")
                .role(Role.SITE)
                .tenant(siteTenant)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .build();

        patientUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("jane.doe@example.com")
                .displayName("Jane Doe")
                .role(Role.PATIENT)
                .tenant(siteTenant)
                .status(UserStatus.PENDING_VERIFICATION)
                .isActive(false)
                .build();

        patientDetail = PatientDetailEntity.builder()
                .id(UUID.randomUUID())
                .user(patientUser)
                .firstName("Jane")
                .lastName("Doe")
                .invitationCode("INV-TEST-12345")
                .assignedUser(siteUser)
                .termsAccepted(false)
                .privacyPolicyAccepted(false)
                .healthDataConsentAccepted(false)
                .consentedAt(Instant.now())
                .build();
    }

    @Test
    @DisplayName("invitePatient stages patient, assigns caller, and dispatches email")
    void invitePatient_success() {
        PatientInviteRequest request = PatientInviteRequest.builder()
                .firstName("Jane")
                .lastName("Doe")
                .email("jane.doe@example.com")
                .phoneNumber("+15551234567")
                .build();

        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));
        when(userRepository.existsByEmail("jane.doe@example.com")).thenReturn(false);
        when(userRepository.existsByPhoneNumber("+15551234567")).thenReturn(false);
        when(firebaseService.getUserByEmail("jane.doe@example.com")).thenReturn(Optional.empty());
        when(userRepository.save(any(UserEntity.class))).thenAnswer(inv -> inv.getArgument(0));
        when(patientDetailRepository.save(any(PatientDetailEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        PatientInviteResponse response = patientService.invitePatient(request, siteUser.getId());

        assertThat(response).isNotNull();
        assertThat(response.getEmail()).isEqualTo("jane.doe@example.com");
        assertThat(response.getTenantId()).isEqualTo(siteTenant.getId());
        assertThat(response.getAssignedUserId()).isEqualTo(siteUser.getId());
        assertThat(response.getInvitationCode()).startsWith("INV-");

        verify(notificationServiceClient).sendPatientInvitationEmail(
                eq("jane.doe@example.com"),
                eq("Dr. Alice Smith"),
                eq("Mayo Clinic Site"),
                anyString(),
                anyString()
        );
    }

    @Test
    @DisplayName("invitePatient fails when caller is not SPONSOR or SITE")
    void invitePatient_invalidRole_throwsUnauthorized() {
        UserEntity patientCaller = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("pat@hekma.com")
                .role(Role.PATIENT)
                .tenant(siteTenant)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .build();

        PatientInviteRequest request = PatientInviteRequest.builder()
                .firstName("Jane")
                .lastName("Doe")
                .email("jane.doe@example.com")
                .build();

        when(userRepository.findById(patientCaller.getId())).thenReturn(Optional.of(patientCaller));

        assertThatThrownBy(() -> patientService.invitePatient(request, patientCaller.getId()))
                .isInstanceOf(UnauthorizedOperationException.class)
                .hasMessageContaining("Only SPONSOR or SITE");
    }

    @Test
    @DisplayName("invitePatient fails when inviter tenant is suspended")
    void invitePatient_suspendedTenant_throwsTenantSuspended() {
        siteTenant.setStatus(TenantStatus.SUSPENDED);

        PatientInviteRequest request = PatientInviteRequest.builder()
                .firstName("Jane")
                .lastName("Doe")
                .email("jane.doe@example.com")
                .build();

        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));

        assertThatThrownBy(() -> patientService.invitePatient(request, siteUser.getId()))
                .isInstanceOf(TenantSuspendedException.class);
    }

    @Test
    @DisplayName("invitePatient fails when email already exists")
    void invitePatient_duplicateEmail_throwsConflict() {
        PatientInviteRequest request = PatientInviteRequest.builder()
                .firstName("Jane")
                .lastName("Doe")
                .email("jane.doe@example.com")
                .build();

        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));
        when(userRepository.existsByEmail("jane.doe@example.com")).thenReturn(true);

        assertThatThrownBy(() -> patientService.invitePatient(request, siteUser.getId()))
                .isInstanceOf(UserAlreadyExistsException.class);
    }

    @Test
    @DisplayName("acceptInvite validates token and consents, creates Firebase user, and activates account")
    void acceptInvite_success() {
        PatientAcceptInviteRequest request = PatientAcceptInviteRequest.builder()
                .invitationToken("INV-TEST-12345")
                .password("Password123!")
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .build();

        when(patientDetailRepository.findByInvitationCode("INV-TEST-12345")).thenReturn(Optional.of(patientDetail));
        when(firebaseService.createUser(eq("jane.doe@example.com"), eq("Password123!"), eq("Jane Doe"), eq(Role.PATIENT)))
                .thenReturn(FirebaseUserDto.builder().uid("fb-patient-1122").email("jane.doe@example.com").build());
        when(userRepository.save(any(UserEntity.class))).thenAnswer(inv -> inv.getArgument(0));
        when(patientDetailRepository.save(any(PatientDetailEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        PatientResponse response = patientService.acceptInvite(request);

        assertThat(response).isNotNull();
        assertThat(response.getStatus()).isEqualTo(UserStatus.ACTIVE);
        assertThat(response.getIsActive()).isTrue();
        assertThat(response.getTermsAccepted()).isTrue();
        assertThat(response.getPrivacyPolicyAccepted()).isTrue();
        assertThat(response.getHealthDataConsentAccepted()).isTrue();

        verify(firebaseService).assignClaims("fb-patient-1122", Role.PATIENT, siteTenant.getId());
    }

    @Test
    @DisplayName("acceptInvite fails when required consents are missing")
    void acceptInvite_missingConsents_throwsIllegalArgument() {
        PatientAcceptInviteRequest request = PatientAcceptInviteRequest.builder()
                .invitationToken("INV-TEST-12345")
                .password("Password123!")
                .termsAccepted(true)
                .privacyPolicyAccepted(false) // Not accepted!
                .healthDataConsentAccepted(true)
                .build();

        assertThatThrownBy(() -> patientService.acceptInvite(request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Consents must all be accepted");
    }

    @Test
    @DisplayName("acceptInvite fails when invitation token is invalid")
    void acceptInvite_invalidToken_throwsException() {
        PatientAcceptInviteRequest request = PatientAcceptInviteRequest.builder()
                .invitationToken("INVALID-TOKEN")
                .password("Password123!")
                .termsAccepted(true)
                .privacyPolicyAccepted(true)
                .healthDataConsentAccepted(true)
                .build();

        when(patientDetailRepository.findByInvitationCode("INVALID-TOKEN")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> patientService.acceptInvite(request))
                .isInstanceOf(InvalidInvitationException.class);
    }

    @Test
    @DisplayName("listPatients filters by tenant for SITE caller")
    void listPatients_scopedToTenant() {
        PageRequest pageRequest = PageRequest.of(0, 10);
        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));
        when(patientDetailRepository.findByUser_Tenant_PathStartingWith(siteTenant.getPath(), pageRequest))
                .thenReturn(new PageImpl<>(List.of(patientDetail)));

        Page<PatientResponse> page = patientService.listPatients(siteUser.getId(), false, null, pageRequest);

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getContent().get(0).getTenantId()).isEqualTo(siteTenant.getId());
    }

    @Test
    @DisplayName("getPatientById forbids cross-tenant access for SITE caller")
    void getPatientById_crossTenantAccess_throwsUnauthorized() {
        UserEntity otherPatientUser = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("other@roche.com")
                .role(Role.PATIENT)
                .tenant(otherTenant) // Different tenant!
                .build();

        PatientDetailEntity otherPatientDetail = PatientDetailEntity.builder()
                .id(UUID.randomUUID())
                .user(otherPatientUser)
                .firstName("Other")
                .lastName("Patient")
                .build();

        when(patientDetailRepository.findByUserId(otherPatientUser.getId())).thenReturn(Optional.of(otherPatientDetail));
        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));

        assertThatThrownBy(() -> patientService.getPatientById(otherPatientUser.getId(), siteUser.getId()))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessageContaining("Patient profile not found");
    }

    @Test
    @DisplayName("assignPatient successfully reassigns patient to another investigator in same tenant")
    void assignPatient_success() {
        PatientAssignRequest request = PatientAssignRequest.builder()
                .assignedUserId(anotherSiteUser.getId())
                .build();

        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));
        when(patientDetailRepository.findByUserId(patientUser.getId())).thenReturn(Optional.of(patientDetail));
        when(userRepository.findById(anotherSiteUser.getId())).thenReturn(Optional.of(anotherSiteUser));
        when(patientDetailRepository.save(any(PatientDetailEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        PatientResponse response = patientService.assignPatient(patientUser.getId(), request, siteUser.getId());

        assertThat(response).isNotNull();
        assertThat(response.getAssignedUserId()).isEqualTo(anotherSiteUser.getId());
    }

    @Test
    @DisplayName("assignPatient hides investigators outside the operator's subtree (404)")
    void assignPatient_crossTenant_throwsUnauthorized() {
        UserEntity investigatorInOtherTenant = UserEntity.builder()
                .id(UUID.randomUUID())
                .email("investigator@roche.com")
                .role(Role.SPONSOR)
                .tenant(otherTenant) // Different tenant!
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .build();

        PatientAssignRequest request = PatientAssignRequest.builder()
                .assignedUserId(investigatorInOtherTenant.getId())
                .build();

        when(userRepository.findById(siteUser.getId())).thenReturn(Optional.of(siteUser));
        when(patientDetailRepository.findByUserId(patientUser.getId())).thenReturn(Optional.of(patientDetail));
        when(userRepository.findById(investigatorInOtherTenant.getId())).thenReturn(Optional.of(investigatorInOtherTenant));

        assertThatThrownBy(() -> patientService.assignPatient(patientUser.getId(), request, siteUser.getId()))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessageContaining("Target investigator not found");
    }
}
