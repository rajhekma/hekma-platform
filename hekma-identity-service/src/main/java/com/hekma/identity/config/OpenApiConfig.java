package com.hekma.identity.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import io.swagger.v3.oas.models.tags.Tag;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Hekma Identity Service API")
                        .version("1.0.0")
                        .description("Enterprise identity and authentication microservice for the Hekma Platform. " +
                                "Provides user registration, Firebase Authentication synchronization, " +
                                "role-based access management, and dedicated patient onboarding with consent tracking.")
                        .contact(new Contact()
                                .name("Hekma Platform Team")
                                .email("dev@hekma.com")
                                .url("https://hekma.com"))
                        .license(new License()
                                .name("Proprietary")
                                .url("https://hekma.com/terms")))
                .servers(List.of(
                        new Server().url("http://localhost:8080").description("Local Development Server")
                ))
                .tags(List.of(
                        new Tag().name("Authentication")
                                .description("Endpoints for user registration, authentication, token refresh, and OTP verification"),
                        new Tag().name("User Management")
                                .description("Endpoints for managing user status, active/inactive state, and soft deletion"),
                        new Tag().name("System Administration")
                                .description("Administrative operations strictly reserved for the SYSTEM_ADMIN")
                ))
                .components(new Components()
                        .addSecuritySchemes("bearerAuth", new SecurityScheme()
                                .name("bearerAuth")
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                                .description("Firebase ID Token (Bearer JWT)")));
    }
}
