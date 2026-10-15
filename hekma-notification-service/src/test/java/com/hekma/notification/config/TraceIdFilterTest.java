package com.hekma.notification.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

class TraceIdFilterTest {

    private TraceIdFilter traceIdFilter;

    @BeforeEach
    void setUp() {
        traceIdFilter = new TraceIdFilter();
        MDC.clear();
    }

    @AfterEach
    void tearDown() {
        MDC.clear();
    }

    @Test
    @DisplayName("Preserves incoming X-Trace-Id header and sets on response and MDC")
    void preservesIncomingXTraceId() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.TRACE_ID_HEADER, "custom-trace-notify-123");
        MockHttpServletResponse response = new MockHttpServletResponse();

        AtomicReference<String> mdcTraceIdDuringChain = new AtomicReference<>();
        FilterChain filterChain = (req, res) -> mdcTraceIdDuringChain.set(MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY));

        traceIdFilter.doFilter(request, response, filterChain);

        assertThat(mdcTraceIdDuringChain.get()).isEqualTo("custom-trace-notify-123");
        assertThat(response.getHeader(TraceIdFilter.TRACE_ID_HEADER)).isEqualTo("custom-trace-notify-123");
        assertThat(response.getHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER)).isEqualTo("custom-trace-notify-123");
        assertThat(MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY)).isNull();
    }

    @Test
    @DisplayName("Preserves incoming lowercase trace-id header if X-Trace-Id absent")
    void preservesIncomingTraceIdLower() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER, "custom-trace-lower-notify");
        MockHttpServletResponse response = new MockHttpServletResponse();

        AtomicReference<String> mdcTraceIdDuringChain = new AtomicReference<>();
        FilterChain filterChain = (req, res) -> mdcTraceIdDuringChain.set(MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY));

        traceIdFilter.doFilter(request, response, filterChain);

        assertThat(mdcTraceIdDuringChain.get()).isEqualTo("custom-trace-lower-notify");
        assertThat(response.getHeader(TraceIdFilter.TRACE_ID_HEADER)).isEqualTo("custom-trace-lower-notify");
        assertThat(response.getHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER)).isEqualTo("custom-trace-lower-notify");
        assertThat(MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY)).isNull();
    }

    @Test
    @DisplayName("Generates new UUID traceId when incoming headers are missing")
    void generatesNewTraceIdWhenMissing() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        AtomicReference<String> mdcTraceIdDuringChain = new AtomicReference<>();
        FilterChain filterChain = (req, res) -> mdcTraceIdDuringChain.set(MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY));

        traceIdFilter.doFilter(request, response, filterChain);

        assertThat(mdcTraceIdDuringChain.get()).isNotNull().isNotBlank();
        assertThat(response.getHeader(TraceIdFilter.TRACE_ID_HEADER)).isEqualTo(mdcTraceIdDuringChain.get());
        assertThat(response.getHeader(TraceIdFilter.TRACE_ID_HEADER_LOWER)).isEqualTo(mdcTraceIdDuringChain.get());
        assertThat(MDC.get(TraceIdFilter.TRACE_ID_MDC_KEY)).isNull();
    }
}
