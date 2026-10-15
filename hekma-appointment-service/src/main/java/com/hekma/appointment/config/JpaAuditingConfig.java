package com.hekma.appointment.config;

import com.hekma.appointment.security.AppointmentPrincipal;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfig {

    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> {
            Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
            if (authentication == null || !authentication.isAuthenticated()) {
                return Optional.of("SYSTEM");
            }

            Object principal = authentication.getPrincipal();
            if (principal instanceof AppointmentPrincipal ap) {
                return Optional.ofNullable(ap.userId() != null ? ap.userId().toString() : ap.email());
            }

            return Optional.ofNullable(authentication.getName()).filter(name -> !name.isBlank()).or(() -> Optional.of("SYSTEM"));
        };
    }
}
