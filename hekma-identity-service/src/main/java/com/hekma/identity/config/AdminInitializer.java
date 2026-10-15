package com.hekma.identity.config;

import com.hekma.identity.service.AuthService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
@Slf4j
public class AdminInitializer implements ApplicationRunner {

    private final AuthService authService;
    private final PlatformAdminProperties properties;

    public AdminInitializer(AuthService authService, PlatformAdminProperties properties) {
        this.authService = authService;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!properties.isEnabled()) {
            log.info("Platform Admin auto-initialization is disabled.");
            return;
        }

        try {
            log.info("Checking and initializing default Platform Admin user...");
            authService.initializePlatformAdmin(
                    properties.getEmail(),
                    properties.getDisplayName()
            );
            log.info("Platform Admin verification complete. [Email: {}]", properties.getEmail());
        } catch (Exception e) {
            log.error("Failed during Platform Admin initialization: {}", e.getMessage(), e);
        }
    }
}
