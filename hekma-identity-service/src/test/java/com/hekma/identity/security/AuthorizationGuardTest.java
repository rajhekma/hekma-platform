package com.hekma.identity.security;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Build guard (RBAC Phase 3): every application REST and GraphQL handler declares an authorization rule
 * ({@code @PreAuthorize} on the method or class), unless it is an explicitly public endpoint listed in
 * {@link com.hekma.identity.config.SecurityConfig}. A new endpoint without a rule fails the build.
 */
@SpringBootTest
class AuthorizationGuardTest {

    @Autowired
    @Qualifier("requestMappingHandlerMapping")
    private RequestMappingHandlerMapping handlerMapping;

    @Autowired
    private ApplicationContext context;

    private static final Set<String> PUBLIC_POST_PATHS = Set.of(
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
            "/api/v1/users/accept-invite");

    @Test
    @DisplayName("Every REST handler has @PreAuthorize or is an explicitly public endpoint")
    void everyRestHandlerIsProtectedOrPublic() {
        List<String> unprotected = new ArrayList<>();
        for (Map.Entry<RequestMappingInfo, HandlerMethod> entry : handlerMapping.getHandlerMethods().entrySet()) {
            HandlerMethod handler = entry.getValue();
            if (!handler.getBeanType().getPackageName().startsWith("com.hekma.identity")) {
                continue;
            }
            if (hasPreAuthorize(handler.getMethod(), handler.getBeanType())) {
                continue;
            }
            Set<String> paths = entry.getKey().getPatternValues();
            Set<RequestMethod> methods = entry.getKey().getMethodsCondition().getMethods();
            boolean isPublic = methods.equals(Set.of(RequestMethod.POST)) && PUBLIC_POST_PATHS.containsAll(paths);
            if (!isPublic) {
                unprotected.add(methods + " " + paths + " -> " + handler.getShortLogMessage());
            }
        }
        assertThat(unprotected).as("Handlers without @PreAuthorize that are not declared public").isEmpty();
    }

    @Test
    @DisplayName("The public endpoint list in this test matches SecurityConfig")
    void publicListMatchesSecurityConfig() throws Exception {
        var field = com.hekma.identity.config.SecurityConfig.class.getDeclaredField("PUBLIC_POST_ENDPOINTS");
        field.setAccessible(true);
        Set<String> configured = Arrays.stream((String[]) field.get(null)).collect(Collectors.toSet());
        assertThat(configured).isEqualTo(PUBLIC_POST_PATHS);
    }

    @Test
    @DisplayName("Every GraphQL handler has @PreAuthorize")
    void everyGraphQlHandlerIsProtected() {
        List<String> unprotected = new ArrayList<>();
        for (Object bean : context.getBeansWithAnnotation(Controller.class).values()) {
            Class<?> type = org.springframework.aop.support.AopUtils.getTargetClass(bean);
            if (!type.getPackageName().startsWith("com.hekma.identity")) {
                continue;
            }
            for (Method method : type.getDeclaredMethods()) {
                boolean graphQl = AnnotatedElementUtils.hasAnnotation(method, QueryMapping.class)
                        || AnnotatedElementUtils.hasAnnotation(method, MutationMapping.class)
                        || AnnotatedElementUtils.hasAnnotation(method, SchemaMapping.class)
                        || AnnotatedElementUtils.hasAnnotation(method, BatchMapping.class);
                if (graphQl && !hasPreAuthorize(method, type)) {
                    unprotected.add(type.getSimpleName() + "." + method.getName());
                }
            }
        }
        assertThat(unprotected).as("GraphQL handlers without @PreAuthorize").isEmpty();
    }

    private static boolean hasPreAuthorize(Method method, Class<?> type) {
        return AnnotatedElementUtils.hasAnnotation(method, PreAuthorize.class)
                || AnnotatedElementUtils.hasAnnotation(type, PreAuthorize.class);
    }
}
