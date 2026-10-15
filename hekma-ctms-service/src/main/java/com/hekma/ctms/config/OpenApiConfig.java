package com.hekma.ctms.config;

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
                        .title("Hekma CTMS Service API")
                        .version("1.0.0")
                        .description("Clinical Trial Management System microservice for the Hekma Platform. " +
                                "Manages clinical studies, protocols, study arms, study sites, patient progress, " +
                                "queries, adverse events, and EDC webhook integrations.")
                        .contact(new Contact()
                                .name("Hekma Platform Team")
                                .email("dev@hekma.com")
                                .url("https://hekma.com"))
                        .license(new License()
                                .name("Proprietary")
                                .url("https://hekma.com/terms")))
                .servers(List.of(
                        new Server().url("http://localhost:8082").description("Local Development Server")
                ))
                .tags(List.of(
                        new Tag().name("Studies").description("Endpoints for clinical study protocol definition and lifecycle"),
                        new Tag().name("Study Sites").description("Endpoints for study-site allocations, personnel, and notes"),
                        new Tag().name("Adverse Events").description("Endpoints for logging and tracking clinical adverse events"),
                        new Tag().name("Queries").description("Endpoints for sponsor-site protocol queries"),
                        new Tag().name("Schedules & Visits").description("Endpoints for visit templates and patient progress"),
                        new Tag().name("EDC Webhooks").description("Clinical data ingestion from external Electronic Data Capture (EDC) systems")
                ))
                .addSecurityItem(new SecurityRequirement().addList("bearerAuth"))
                .components(new Components()
                        .addSecuritySchemes("bearerAuth", new SecurityScheme()
                                .name("bearerAuth")
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                                .description("Firebase ID Token (Bearer JWT) verified via Identity Introspection")));
    }
}
