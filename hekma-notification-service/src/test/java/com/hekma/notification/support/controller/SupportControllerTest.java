package com.hekma.notification.support.controller;

import com.hekma.notification.config.GlobalExceptionHandler;
import com.hekma.notification.support.config.SupportProperties;
import com.hekma.notification.support.dto.SupportCategoryOptionDto;
import com.hekma.notification.support.dto.SupportTicketSummaryStatsDto;
import com.hekma.notification.support.service.SupportTicketService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Arrays;
import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class SupportControllerTest {

    private MockMvc mockMvc;

    @Mock
    private SupportTicketService supportTicketService;

    private SupportProperties supportProperties;
    private SupportController supportController;

    @BeforeEach
    void setUp() {
        supportProperties = new SupportProperties();
        supportController = new SupportController(supportTicketService, supportProperties);
        mockMvc = MockMvcBuilders.standaloneSetup(supportController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void listCategories_returnsOk() throws Exception {
        List<SupportCategoryOptionDto> categories = Arrays.asList(
                new SupportCategoryOptionDto("LOGIN_ISSUE", "Login Issue"),
                new SupportCategoryOptionDto("APP_CRASH", "App Crash")
        );
        when(supportTicketService.listCategories()).thenReturn(categories);

        mockMvc.perform(get("/api/v1/support/categories"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data[0].code").value("LOGIN_ISSUE"));
    }

    @Test
    void getSummary_unauthorizedWithoutUser() throws Exception {
        mockMvc.perform(get("/api/v1/support/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(401));
    }

    @Test
    void getSummary_successWithUserHeaders() throws Exception {
        SupportTicketSummaryStatsDto stats = new SupportTicketSummaryStatsDto(2, 5);
        when(supportTicketService.resolveAuthenticatedUserEmail("user-1", "user@example.com")).thenReturn("user@example.com");
        when(supportTicketService.getMyTicketSummary("user-1", "user@example.com")).thenReturn(stats);

        mockMvc.perform(get("/api/v1/support/summary")
                        .header("X-User-Id", "user-1")
                        .header("X-User-Email", "user@example.com"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.openCount").value(2))
                .andExpect(jsonPath("$.data.resolvedCount").value(5));
    }
}
