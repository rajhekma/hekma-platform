package com.hekma.identity.config;

import com.hekma.identity.service.AuthService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.boot.DefaultApplicationArguments;

import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class SystemAdminInitializerTest {

    @Mock
    private AuthService authService;

    @Mock
    private SystemAdminProperties properties;

    @InjectMocks
    private SystemAdminInitializer initializer;

    @Test
    @DisplayName("Initializes system admin when enabled is true")
    void run_whenEnabled_callsAuthService() {
        when(properties.isEnabled()).thenReturn(true);
        when(properties.getEmail()).thenReturn("admin@hekma.com");
        when(properties.getDisplayName()).thenReturn("Admin");

        initializer.run(new DefaultApplicationArguments());

        verify(authService).initializeSystemAdmin("admin@hekma.com", "Admin");
    }

    @Test
    @DisplayName("Does not initialize system admin when enabled is false")
    void run_whenDisabled_doesNotCallAuthService() {
        when(properties.isEnabled()).thenReturn(false);

        initializer.run(new DefaultApplicationArguments());

        verifyNoInteractions(authService);
    }

    @Test
    @DisplayName("Catches and handles exception gracefully without throwing")
    void run_whenExceptionOccurs_handlesGracefully() {
        when(properties.isEnabled()).thenReturn(true);
        when(properties.getEmail()).thenReturn("admin@hekma.com");
        when(properties.getDisplayName()).thenReturn("Admin");
        doThrow(new RuntimeException("DB down")).when(authService).initializeSystemAdmin(anyString(), anyString());

        initializer.run(new DefaultApplicationArguments());

        verify(authService).initializeSystemAdmin("admin@hekma.com", "Admin");
    }
}
