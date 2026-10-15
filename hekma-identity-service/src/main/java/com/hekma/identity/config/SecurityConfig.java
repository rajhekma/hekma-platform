package com.hekma.identity.config;

import com.hekma.identity.firebase.FirebaseService;
import com.hekma.identity.multitenancy.TenantFilter;
import com.hekma.identity.repository.TenantRepository;
import com.hekma.identity.repository.UserAuthorityRepository;
import com.hekma.identity.repository.UserRepository;
import com.hekma.identity.security.FirebaseAuthenticationFilter;
import com.hekma.identity.security.SecurityErrorWriter;
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
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

/**
 * Deny-by-default security configuration.
 * <p>
 * Only the endpoints listed in {@link #PUBLIC_POST_ENDPOINTS} (and API docs / GraphiQL when enabled) are
 * reachable without a Firebase ID token. Every other request requires {@code Authorization: Bearer <idToken>};
 * the caller's identity, role and tenant are resolved from the database by {@link FirebaseAuthenticationFilter}.
 * Fine-grained rules are declared with {@code @PreAuthorize} on each handler.
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    /**
     * Unauthenticated operations, declared by exact method and path.
     */
    public static final String[] PUBLIC_POST_ENDPOINTS = {
            "/api/v1/auth/register",
            "/api/v1/auth/register-tenant",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh-token",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password",
            "/api/v1/auth/otp/send",
            "/api/v1/auth/otp/verify",
            "/api/v1/auth/otp/resend",
            "/api/v1/patients/accept-invite",
            "/api/v1/users/accept-invite"
    };

    private static final String[] API_DOCS_ENDPOINTS = {
            "/swagger-ui/**",
            "/swagger-ui.html",
            "/v3/api-docs/**",
            "/swagger-resources/**",
            "/webjars/**"
    };

    private final FirebaseService firebaseService;
    private final UserRepository userRepository;
    private final TenantRepository tenantRepository;
    private final UserAuthorityRepository userAuthorityRepository;
    private final com.hekma.identity.repository.CustomRoleRepository customRoleRepository;
    private final List<String> corsAllowedOrigins;
    private final boolean exposeApiDocs;
    private final boolean graphiqlEnabled;
    private final SecurityErrorWriter errorWriter = new SecurityErrorWriter();

    public SecurityConfig(FirebaseService firebaseService,
                          UserRepository userRepository,
                          TenantRepository tenantRepository,
                          UserAuthorityRepository userAuthorityRepository,
                          com.hekma.identity.repository.CustomRoleRepository customRoleRepository,
                          @Value("${app.security.cors.allowed-origins:http://localhost:3000}") List<String> corsAllowedOrigins,
                          @Value("${app.security.expose-api-docs:false}") boolean exposeApiDocs,
                          @Value("${spring.graphql.graphiql.enabled:true}") boolean graphiqlEnabled) {
        this.firebaseService = firebaseService;
        this.userRepository = userRepository;
        this.tenantRepository = tenantRepository;
        this.userAuthorityRepository = userAuthorityRepository;
        this.customRoleRepository = customRoleRepository;
        this.corsAllowedOrigins = corsAllowedOrigins;
        this.exposeApiDocs = exposeApiDocs;
        this.graphiqlEnabled = graphiqlEnabled;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(corsAllowedOrigins);
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-Tenant-ID", "X-Trace-Id", "trace-id", "X-Request-Id"));
        configuration.setExposedHeaders(List.of("X-Trace-Id", "trace-id"));
        configuration.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        FirebaseAuthenticationFilter authenticationFilter = new FirebaseAuthenticationFilter(firebaseService, userRepository, tenantRepository, userAuthorityRepository, customRoleRepository, errorWriter);
        TenantFilter tenantFilter = new TenantFilter(tenantRepository, errorWriter);

        http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> {
                    auth.requestMatchers(HttpMethod.POST, PUBLIC_POST_ENDPOINTS).permitAll();
                    auth.requestMatchers("/error").permitAll();
                    if (exposeApiDocs) {
                        auth.requestMatchers(API_DOCS_ENDPOINTS).permitAll();
                    }
                    if (graphiqlEnabled) {
                        auth.requestMatchers("/graphiql", "/graphiql/**").permitAll();
                    }
                    auth.anyRequest().authenticated();
                })
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, e) ->
                                errorWriter.write(response, HttpStatus.UNAUTHORIZED, "Authentication is required to access this resource."))
                        .accessDeniedHandler((request, response, e) ->
                                errorWriter.write(response, HttpStatus.FORBIDDEN, "You do not have permission to perform this operation.")))
                .addFilterBefore(authenticationFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterAfter(tenantFilter, FirebaseAuthenticationFilter.class)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
