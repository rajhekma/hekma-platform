package com.hekma.identity.config;

import com.hekma.identity.service.AuthService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
@Slf4j
public class SystemAdminInitializer implements ApplicationRunner {

    private final AuthService authService;
    private final SystemAdminProperties properties;

    public SystemAdminInitializer(AuthService authService, SystemAdminProperties properties) {
        this.authService = authService;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!properties.isEnabled()) {
            log.info("System Admin auto-initialization is disabled.");
            return;
        }

        try {
            log.info("Checking and initializing default System Admin user...");
            authService.initializeSystemAdmin(
                    properties.getEmail(),
                    properties.getDisplayName()
            );
            log.info("System Admin verification complete. [Email: {}]", properties.getEmail());
        } catch (Exception e) {
            log.error("Failed during System Admin initialization: {}", e.getMessage(), e);
        }
    }
}
