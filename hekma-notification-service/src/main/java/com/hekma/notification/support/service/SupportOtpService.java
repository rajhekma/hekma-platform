package com.hekma.notification.support.service;

import com.hekma.notification.domain.model.NotificationChannel;
import com.hekma.notification.domain.model.NotificationPriority;
import com.hekma.notification.dto.NotificationSendRequest;
import com.hekma.notification.service.NotificationDispatcherService;
import com.hekma.notification.support.config.SupportProperties;
import com.hekma.notification.support.domain.entity.SupportOtpVerificationEntity;
import com.hekma.notification.support.domain.repository.SupportOtpVerificationEntityRepository;
import com.hekma.notification.support.dto.SupportOtpResultDto;
import com.hekma.notification.support.dto.SupportOtpVerifyResultDto;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Date;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Slf4j
@Service
public class SupportOtpService {

    private final SecureRandom secureRandom = new SecureRandom();
    private final SupportOtpVerificationEntityRepository otpRepository;
    private final NotificationDispatcherService notificationDispatcherService;
    private final SupportProperties supportProperties;

    // In-memory lockout and rate-limiting cache (email -> lockout/cooldown expiry timestamp)
    private final ConcurrentHashMap<String, Long> emailLockouts = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Long> emailResendCooldowns = new ConcurrentHashMap<>();

    public SupportOtpService(SupportOtpVerificationEntityRepository otpRepository,
                             NotificationDispatcherService notificationDispatcherService,
                             SupportProperties supportProperties) {
        this.otpRepository = otpRepository;
        this.notificationDispatcherService = notificationDispatcherService;
        this.supportProperties = supportProperties;
    }

    @Transactional
    public SupportOtpResultDto sendOtp(String email) {
        SupportOtpResultDto result = new SupportOtpResultDto();
        String normalizedEmail = normalizeEmail(email);

        if (normalizedEmail == null) {
            result.setSuccess(false);
            result.setMessage("A valid email address is required.");
            return result;
        }

        long now = System.currentTimeMillis();
        Long lockedUntil = emailLockouts.get(normalizedEmail);
        if (lockedUntil != null && lockedUntil > now) {
            int retryAfter = (int) ((lockedUntil - now) / 1000);
            result.setSuccess(false);
            result.setMessage("Too many attempts. Please try again later.");
            result.setRetryAfter(retryAfter);
            return result;
        }

        Long cooldownUntil = emailResendCooldowns.get(normalizedEmail);
        if (cooldownUntil != null && cooldownUntil > now) {
            int retryAfter = (int) ((cooldownUntil - now) / 1000);
            result.setSuccess(false);
            result.setMessage("Please wait before requesting another code.");
            result.setRetryAfter(retryAfter);
            return result;
        }

        String challengeId = UUID.randomUUID().toString();
        String otp = generateOtpCode();
        String otpHash = hashOtp(challengeId, otp);
        long ttlSeconds = supportProperties.getOtp().getTtlSeconds();

        SupportOtpVerificationEntity entity = new SupportOtpVerificationEntity();
        entity.setEmail(normalizedEmail);
        entity.setOtpHash(otpHash);
        entity.setChallengeId(challengeId);
        entity.setAttempts(0);
        entity.setVerified(false);
        entity.setExpiresAt(new Date(now + ttlSeconds * 1000));
        otpRepository.save(entity);

        try {
            sendOtpEmail(normalizedEmail, otp);
        } catch (Exception e) {
            log.error("Failed to dispatch support OTP email to {}", maskEmail(normalizedEmail), e);
            result.setSuccess(false);
            result.setMessage("We could not send the verification code. Please try again.");
            return result;
        }

        long cooldownMillis = supportProperties.getOtp().getResendCooldownSeconds() * 1000;
        emailResendCooldowns.put(normalizedEmail, now + cooldownMillis);

        result.setSuccess(true);
        result.setChallengeId(challengeId);
        result.setMaskedEmail(maskEmail(normalizedEmail));
        result.setExpiry((int) ttlSeconds);
        result.setMessage("Verification code sent.");
        return result;
    }

    @Transactional
    public SupportOtpVerifyResultDto verifyOtp(String challengeId, String otpCode) {
        SupportOtpVerifyResultDto result = new SupportOtpVerifyResultDto();

        if (challengeId == null || challengeId.trim().isEmpty() || otpCode == null || otpCode.trim().isEmpty()) {
            result.setSuccess(false);
            result.setMessage("Challenge ID and OTP code are required.");
            return result;
        }

        Optional<SupportOtpVerificationEntity> optionalEntity = otpRepository.findByChallengeId(challengeId.trim());
        if (optionalEntity.isEmpty()) {
            result.setSuccess(false);
            result.setMessage("Verification code expired or not found.");
            return result;
        }

        SupportOtpVerificationEntity entity = optionalEntity.get();
        if (entity.getExpiresAt().before(new Date())) {
            result.setSuccess(false);
            result.setMessage("Verification code expired or not found.");
            return result;
        }

        if (Boolean.TRUE.equals(entity.getVerified())) {
            result.setSuccess(false);
            result.setMessage("This code has already been used.");
            return result;
        }

        String normalizedEmail = entity.getEmail();
        long now = System.currentTimeMillis();
        Long lockedUntil = emailLockouts.get(normalizedEmail);
        if (lockedUntil != null && lockedUntil > now) {
            result.setSuccess(false);
            result.setMessage("Too many failed attempts. Please try again later.");
            return result;
        }

        String expectedHash = hashOtp(challengeId.trim(), otpCode.trim());
        if (!expectedHash.equals(entity.getOtpHash())) {
            entity.setAttempts(entity.getAttempts() + 1);
            otpRepository.save(entity);
            if (entity.getAttempts() >= supportProperties.getOtp().getMaxAttempts()) {
                long lockMillis = supportProperties.getOtp().getLockTtlSeconds() * 1000;
                emailLockouts.put(normalizedEmail, now + lockMillis);
            }
            result.setSuccess(false);
            result.setMessage("Invalid verification code.");
            return result;
        }

        String sessionToken = UUID.randomUUID().toString().replace("-", "");
        long sessionTtl = supportProperties.getOtp().getSessionTtlSeconds();

        entity.setVerified(true);
        entity.setSessionToken(sessionToken);
        entity.setExpiresAt(new Date(now + sessionTtl * 1000));
        otpRepository.save(entity);

        result.setSuccess(true);
        result.setOtpToken(sessionToken);
        result.setEmail(entity.getEmail());
        result.setExpiresIn((int) sessionTtl);
        result.setMessage("Email verified successfully.");
        return result;
    }

    public String validateSessionToken(String otpToken) {
        if (otpToken == null || otpToken.trim().isEmpty()) {
            return null;
        }
        return otpRepository.findBySessionToken(otpToken.trim())
                .filter(e -> Boolean.TRUE.equals(e.getVerified()))
                .filter(e -> e.getExpiresAt() != null && e.getExpiresAt().after(new Date()))
                .map(SupportOtpVerificationEntity::getEmail)
                .orElse(null);
    }

    public String normalizeEmail(String email) {
        if (email == null) {
            return null;
        }
        String trimmed = email.trim().toLowerCase();
        if (!trimmed.contains("@") || trimmed.length() < 5) {
            return null;
        }
        return trimmed;
    }

    private String generateOtpCode() {
        int code = 100000 + secureRandom.nextInt(900000);
        return String.valueOf(code);
    }

    private String hashOtp(String challengeId, String otp) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            String input = challengeId + ":" + otp + ":" + supportProperties.getOtp().getPepper();
            byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 algorithm not available", e);
        }
    }

    private void sendOtpEmail(String email, String otp) {
        NotificationSendRequest sendRequest = new NotificationSendRequest();
        sendRequest.setChannel(NotificationChannel.EMAIL);
        sendRequest.setRecipient(email);
        sendRequest.setTitle("Your HEKMA Support Verification Code");
        sendRequest.setContent("Your verification code is " + otp + ". This code expires in " +
                (supportProperties.getOtp().getTtlSeconds() / 60) + " minutes.");
        sendRequest.setPriority(NotificationPriority.HIGH);
        sendRequest.setSourceService("hekma-notification-service");
        sendRequest.setAsync(false);

        notificationDispatcherService.sendNotification(sendRequest);
    }

    private String maskEmail(String email) {
        if (email == null || !email.contains("@")) {
            return email;
        }
        int atIndex = email.indexOf('@');
        String name = email.substring(0, atIndex);
        String domain = email.substring(atIndex);
        if (name.length() <= 2) {
            return name.charAt(0) + "***" + domain;
        }
        return name.charAt(0) + "***" + name.charAt(name.length() - 1) + domain;
    }
}
