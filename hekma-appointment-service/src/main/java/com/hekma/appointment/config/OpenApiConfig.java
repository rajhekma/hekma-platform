package com.hekma.appointment.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
        info = @Info(
                title = "Hekma Appointment Service API",
                version = "1.0.0",
                description = "Microservice managing appointment scheduling, requests, reminders, and calendar conflict checks across the Hekma Platform.",
                contact = @Contact(name = "Hekma AI Platform Team", email = "dev@hekma.ai")
        ),
        security = {
                @SecurityRequirement(name = "bearerAuth")
        }
)
@SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT",
        description = "Provide Firebase ID Token without 'Bearer ' prefix"
)
public class OpenApiConfig {
}
