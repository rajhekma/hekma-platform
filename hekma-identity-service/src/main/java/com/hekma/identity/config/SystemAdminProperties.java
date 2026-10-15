package com.hekma.identity.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "app.system-admin")
@Getter
@Setter
public class SystemAdminProperties {

    private String email = "system.admin@hekma.com";
    private String displayName = "System Administrator";
    private boolean enabled = true;
}
