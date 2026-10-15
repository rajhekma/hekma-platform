package com.hekma.appointment.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class TraceIdFilterTest {

    private TraceIdFilter filter;
    private FilterChain filterChain;

    @BeforeEach
    void setUp() {
        filter = new TraceIdFilter();
        filterChain = mock(FilterChain.class);
        MDC.clear();
    }

    @Test
    void generatesNewTraceIdWhenMissing() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/appointments");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        String traceId = response.getHeader(TraceIdFilter.TRACE_ID_HEADER);
        assertNotNull(traceId);
        assertFalse(traceId.isBlank());
        assertEquals(traceId, response.getHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER));
        assertNull(MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY), "MDC must be cleared after filter completion");
        verify(filterChain, times(1)).doFilter(request, response);
    }

    @Test
    void preservesIncomingXTraceIdHeader() throws ServletException, IOException {
        String existingTraceId = "incoming-trace-id-12345";
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/appointments");
        request.addHeader(TraceIdFilter.TRACE_ID_HEADER, existingTraceId);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        assertEquals(existingTraceId, response.getHeader(TraceIdFilter.TRACE_ID_HEADER));
        assertEquals(existingTraceId, response.getHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER));
    }

    @Test
    void preservesIncomingLowerCaseTraceIdHeader() throws ServletException, IOException {
        String existingTraceId = "incoming-kebab-trace-id-67890";
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/appointments");
        request.addHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER, existingTraceId);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        assertEquals(existingTraceId, response.getHeader(TraceIdFilter.TRACE_ID_HEADER));
        assertEquals(existingTraceId, response.getHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER));
    }

    @Test
    void logsRequestLifecycle() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/appointments");
        request.setQueryString("size=100");
        MockHttpServletResponse response = new MockHttpServletResponse();
        response.setStatus(200);

        filter.doFilter(request, response, filterChain);

        String traceId = response.getHeader(TraceIdFilter.TRACE_ID_HEADER);
        assertNotNull(traceId);
        verify(filterChain, times(1)).doFilter(request, response);
    }
}
