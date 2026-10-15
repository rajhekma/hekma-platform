package com.hekma.identity.config;

import com.hekma.identity.security.HekmaPrincipal;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

/**
 * Enables Spring Data JPA Auditing to automatically populate @CreatedDate, @LastModifiedDate,
 * @CreatedBy, and @LastModifiedBy fields on entities extending BaseAuditEntity.
 */
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfig {

    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> {
            Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
            if (authentication == null || !authentication.isAuthenticated() || "anonymousUser".equals(authentication.getPrincipal())) {
                return Optional.of("SYSTEM");
            }
            if (authentication.getPrincipal() instanceof HekmaPrincipal principal) {
                return Optional.of(principal.userId().toString());
            }
            return Optional.ofNullable(authentication.getName());
        };
    }
}
