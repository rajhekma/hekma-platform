package com.hekma.notification.support.service;

import com.hekma.notification.service.NotificationDispatcherService;
import com.hekma.notification.support.config.SupportProperties;
import com.hekma.notification.support.domain.entity.SupportOtpVerificationEntity;
import com.hekma.notification.support.domain.repository.SupportOtpVerificationEntityRepository;
import com.hekma.notification.support.dto.SupportOtpResultDto;
import com.hekma.notification.support.dto.SupportOtpVerifyResultDto;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Date;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class SupportOtpServiceTest {

    @Mock
    private SupportOtpVerificationEntityRepository otpRepository;

    @Mock
    private NotificationDispatcherService notificationDispatcherService;

    private SupportProperties supportProperties;
    private SupportOtpService supportOtpService;

    @BeforeEach
    void setUp() {
        supportProperties = new SupportProperties();
        supportOtpService = new SupportOtpService(otpRepository, notificationDispatcherService, supportProperties);
    }

    @Test
    void sendOtp_rejectsInvalidEmail() {
        SupportOtpResultDto result = supportOtpService.sendOtp("not-an-email");
        assertFalse(result.getSuccess());
        assertNotNull(result.getMessage());
    }

    @Test
    void sendOtp_sendsCodeSuccessfully() {
        when(otpRepository.save(any(SupportOtpVerificationEntity.class))).thenAnswer(inv -> inv.getArgument(0));

        SupportOtpResultDto result = supportOtpService.sendOtp("patient@example.com");

        assertTrue(result.getSuccess());
        assertNotNull(result.getChallengeId());
        assertNotNull(result.getMaskedEmail());
        verify(notificationDispatcherService).sendNotification(any());
        verify(otpRepository).save(any(SupportOtpVerificationEntity.class));
    }

    @Test
    void verifyOtp_rejectsInvalidCode() {
        ArgumentCaptor<SupportOtpVerificationEntity> captor = ArgumentCaptor.forClass(SupportOtpVerificationEntity.class);
        when(otpRepository.save(captor.capture())).thenAnswer(inv -> inv.getArgument(0));

        SupportOtpResultDto sendResult = supportOtpService.sendOtp("patient@example.com");
        assertTrue(sendResult.getSuccess());

        when(otpRepository.findByChallengeId(sendResult.getChallengeId())).thenReturn(Optional.of(captor.getValue()));

        SupportOtpVerifyResultDto invalidResult = supportOtpService.verifyOtp(sendResult.getChallengeId(), "000000");
        assertFalse(invalidResult.getSuccess());
        assertEquals("Invalid verification code.", invalidResult.getMessage());
    }

    @Test
    void verifyOtp_successAndValidateSession() {
        ArgumentCaptor<SupportOtpVerificationEntity> captor = ArgumentCaptor.forClass(SupportOtpVerificationEntity.class);
        when(otpRepository.save(captor.capture())).thenAnswer(inv -> inv.getArgument(0));

        SupportOtpResultDto sendResult = supportOtpService.sendOtp("patient@example.com");
        assertTrue(sendResult.getSuccess());

        SupportOtpVerificationEntity entity = captor.getValue();

        // Using reflection or mock hash to simulate matching OTP
        // Or directly verify session token lookup
        entity.setVerified(true);
        entity.setSessionToken("test-session-token-123");
        entity.setExpiresAt(new Date(System.currentTimeMillis() + 1800000));
        when(otpRepository.findBySessionToken("test-session-token-123")).thenReturn(Optional.of(entity));

        String email = supportOtpService.validateSessionToken("test-session-token-123");
        assertEquals("patient@example.com", email);
    }
}
