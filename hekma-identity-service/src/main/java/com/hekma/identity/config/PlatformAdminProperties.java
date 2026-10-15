package com.hekma.identity.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "app.platform-admin")
@Getter
@Setter
public class PlatformAdminProperties {

    private String email = "admin@hekma.com";
    private String displayName = "Platform Administrator";
    private boolean enabled = true;
}
