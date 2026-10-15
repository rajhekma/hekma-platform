package com.hekma.ctms.config;

import com.hekma.ctms.security.IntrospectionAuthenticationFilter;
import com.hekma.ctms.security.SecurityErrorWriter;
import com.hekma.ctms.security.client.IdentityServiceClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    private static final String[] API_DOCS_ENDPOINTS = {
            "/swagger-ui",
            "/swagger-ui/**",
            "/swagger-ui.html",
            "/v3/api-docs",
            "/v3/api-docs/**",
            "/swagger-resources/**",
            "/webjars/**"
    };

    private static final String[] WEBHOOK_ENDPOINTS = {
            "/webhook/cmts",
            "/webhook/cmts/**",
            "/api/v1/webhook/cmts/**"
    };

    private final IdentityServiceClient identityServiceClient;
    private final List<String> corsAllowedOrigins;
    private final boolean exposeApiDocs;
    private final boolean graphiqlEnabled;
    private final SecurityErrorWriter errorWriter = new SecurityErrorWriter();

    public SecurityConfig(IdentityServiceClient identityServiceClient,
                          @Value("${app.security.cors.allowed-origins:http://localhost:3000}") List<String> corsAllowedOrigins,
                          @Value("${app.security.expose-api-docs:true}") boolean exposeApiDocs,
                          @Value("${spring.graphql.graphiql.enabled:true}") boolean graphiqlEnabled) {
        this.identityServiceClient = identityServiceClient;
        this.corsAllowedOrigins = corsAllowedOrigins;
        this.exposeApiDocs = exposeApiDocs;
        this.graphiqlEnabled = graphiqlEnabled;
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(corsAllowedOrigins);
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-Access-Key", "X-Secret-Key", "X-Trace-Id", "trace-id", "X-Request-Id"));
        configuration.setExposedHeaders(List.of("X-Trace-Id", "trace-id"));
        configuration.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        IntrospectionAuthenticationFilter filter = new IntrospectionAuthenticationFilter(identityServiceClient, errorWriter);

        http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> {
                    auth.requestMatchers("/error").permitAll();
                    if (exposeApiDocs) {
                        auth.requestMatchers(API_DOCS_ENDPOINTS).permitAll();
                    }
                    if (graphiqlEnabled) {
                        auth.requestMatchers("/graphiql", "/graphiql/**").permitAll();
                    }
                    // Webhook endpoints authenticate via X-Access-Key / X-Secret-Key headers
                    auth.requestMatchers(WEBHOOK_ENDPOINTS).permitAll();
                    auth.anyRequest().authenticated();
                })
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, e) ->
                                errorWriter.write(response, HttpStatus.UNAUTHORIZED, "Authentication is required to access this resource."))
                        .accessDeniedHandler((request, response, e) ->
                                errorWriter.write(response, HttpStatus.FORBIDDEN, "You do not have permission to perform this operation.")))
                .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
