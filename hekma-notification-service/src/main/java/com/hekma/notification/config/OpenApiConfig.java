package com.hekma.notification.config;

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

/**
 * OpenAPI 3.0 / Swagger UI configuration for Hekma Notification & Support Service.
 */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Hekma Notification & Support Service API")
                        .version("1.0.0")
                        .description("Centralized microservice responsible for multi-channel notification delivery " +
                                "and customer support ticketing across the Hekma Platform.\n\n" +
                                "### Core Capabilities:\n" +
                                "- **Multi-Channel Notifications**: Asynchronous dispatching across Email (SMTP), SMS (Twilio), " +
                                "Push (Firebase FCM), and persistent In-App notification feeds.\n" +
                                "- **In-App User Feeds**: Paginated user notification inbox, unread counts, and read/delete management.\n" +
                                "- **Support Center & Ticketing**: Public guest ticket creation, OTP email/SMS verification, " +
                                "ticket inquiry, comments, and priority escalation.\n" +
                                "- **Attachments & SLA Tracking**: Direct multipart file uploads, S3 presigned URLs, " +
                                "and automated SLA breach monitoring.")
                        .contact(new Contact()
                                .name("Hekma Platform Team")
                                .email("dev@hekma.com")
                                .url("https://hekma.com"))
                        .license(new License()
                                .name("Proprietary")
                                .url("https://hekma.com/terms")))
                .servers(List.of(
                        new Server().url("http://localhost:8081").description("Local Development Server")
                ))
                .tags(List.of(
                        new Tag().name("Notification Dispatcher")
                                .description("Inter-service endpoints for dispatching multi-channel alerts (Email, SMS, Push, In-App)"),
                        new Tag().name("In-App Notifications")
                                .description("Endpoints for managing user in-app notification inbox, unread badges, and read status"),
                        new Tag().name("Support Center - Public")
                                .description("Guest support endpoints for ticket creation, OTP verification, comment updates, and file uploads"),
                        new Tag().name("Support Center - Management")
                                .description("Support category catalog, ticket summary statistics, and staff/authenticated operations")
                ))
                .components(new Components()
                        .addSecuritySchemes("serviceApiKey", new SecurityScheme()
                                .name("X-Hekma-Service-Key")
                                .type(SecurityScheme.Type.APIKEY)
                                .in(SecurityScheme.In.HEADER)
                                .description("Internal service-to-service authentication header"))
                        .addSecuritySchemes("otpSessionToken", new SecurityScheme()
                                .name("X-Support-Otp-Token")
                                .type(SecurityScheme.Type.APIKEY)
                                .in(SecurityScheme.In.HEADER)
                                .description("OTP verification session token for public ticket access"))
                        .addSecuritySchemes("bearerAuth", new SecurityScheme()
                                .name("bearerAuth")
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                                .description("JWT Bearer token for authenticated support and gateway operations")));
    }
}
