package com.hekma.notification.channel.email;

import com.hekma.notification.channel.NotificationResult;
import jakarta.mail.internet.MimeMessage;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Slf4j
@Component
@ConditionalOnProperty(name = "hekma.notification.channels.email.provider", havingValue = "smtp")
public class SmtpEmailProvider implements EmailProvider {

    private final ObjectProvider<JavaMailSender> mailSenderProvider;
    private final String mailPassword;

    public SmtpEmailProvider(
            ObjectProvider<JavaMailSender> mailSenderProvider,
            @Value("${spring.mail.password:}") String mailPassword) {
        this.mailSenderProvider = mailSenderProvider;
        this.mailPassword = mailPassword;
    }

    @Override
    public NotificationResult sendEmail(String to, String subject, String body, String from) {
        if (mailPassword == null || mailPassword.trim().isEmpty()) {
            String messageId = "mock-smtp-" + UUID.randomUUID();
            log.warn("[SMTP CONFIG WARNING] 'spring.mail.password' is not configured or empty. Falling back to console dispatch.");
            log.info("[MOCK EMAIL DISPATCHED] ID: {} | From: {} | To: {} | Subject: {} | Content: {}",
                    messageId, from, to, subject, body);
            System.out.println("==================================================================");
            System.out.println(">>> [EMAIL NOTIFICATION - CONSOLE FALLBACK] <<<");
            System.out.println(">>> To: " + to);
            System.out.println(">>> Subject: " + subject);
            System.out.println(">>> Content: " + body);
            System.out.println("==================================================================");
            return NotificationResult.success(messageId);
        }

        JavaMailSender mailSender = mailSenderProvider.getIfAvailable();
        if (mailSender == null) {
            log.error("JavaMailSender is not configured in Spring context");
            return NotificationResult.failure("JavaMailSender is not available");
        }

        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom(from);
            helper.setTo(to);
            helper.setSubject(subject != null ? subject : "Hekma Notification");
            helper.setText(body, true);

            mailSender.send(message);
            String messageId = "smtp-" + UUID.randomUUID();
            log.info("Email sent successfully via SMTP to {} (ID: {})", to, messageId);
            System.out.println("==================================================================");
            System.out.println(">>> [EMAIL SENT VIA SMTP GMAIL] <<<");
            System.out.println(">>> From: " + from);
            System.out.println(">>> To: " + to);
            System.out.println(">>> Subject: " + subject);
            System.out.println(">>> Content: " + body);
            System.out.println("==================================================================");
            return NotificationResult.success(messageId);
        } catch (Exception ex) {
            log.error("Failed to send email via SMTP to {}: {}", to, ex.getMessage(), ex);
            System.out.println("==================================================================");
            System.out.println(">>> [SMTP SEND FAILED - CONSOLE FALLBACK PREVIEW] <<<");
            System.out.println(">>> To: " + to);
            System.out.println(">>> Subject: " + subject);
            System.out.println(">>> Content: " + body);
            System.out.println("==================================================================");
            return NotificationResult.failure("SMTP delivery failed: " + ex.getMessage());
        }
    }
}
