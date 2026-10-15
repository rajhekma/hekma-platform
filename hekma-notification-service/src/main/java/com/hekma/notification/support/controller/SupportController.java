package com.hekma.notification.support.controller;

import com.hekma.notification.support.config.SupportProperties;
import com.hekma.notification.support.dto.RestResponse;
import com.hekma.notification.support.dto.SupportCategoryOptionDto;
import com.hekma.notification.support.dto.SupportTicketAttachmentDto;
import com.hekma.notification.support.dto.SupportTicketSummaryStatsDto;
import com.hekma.notification.support.service.SupportTicketService;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.http.HttpServletRequest;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.nio.charset.StandardCharsets;
import io.swagger.v3.oas.annotations.tags.Tag;

import java.security.Key;
import java.util.List;

@Slf4j
@RestController
@RequestMapping("/api/v1/support")
@Tag(name = "Support Center - Management", description = "Endpoints for ticket categories, summaries, and authenticated attachments")
public class SupportController {

    private final SupportTicketService supportTicketService;
    private final SupportProperties supportProperties;

    public SupportController(SupportTicketService supportTicketService,
                             SupportProperties supportProperties) {
        this.supportTicketService = supportTicketService;
        this.supportProperties = supportProperties;
    }

    @GetMapping("/categories")
    public RestResponse<List<SupportCategoryOptionDto>> listCategories() {
        return RestResponse.success("Support categories retrieved.", supportTicketService.listCategories());
    }

    @GetMapping("/summary")
    public RestResponse<SupportTicketSummaryStatsDto> getSummary(HttpServletRequest request) {
        ResolvedUser user = resolveUser(request);
        if (user == null) {
            return RestResponse.error(401, "Authentication required");
        }
        return RestResponse.success("Support summary retrieved.",
                supportTicketService.getMyTicketSummary(
                        user.getUserId(),
                        supportTicketService.resolveAuthenticatedUserEmail(user.getUserId(), user.getEmail())));
    }

    @PostMapping(value = "/tickets/{ticketId}/attachments", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public RestResponse<List<SupportTicketAttachmentDto>> uploadAttachments(
            @PathVariable String ticketId,
            @RequestPart("files") MultipartFile[] files,
            HttpServletRequest request) {
        ResolvedUser user = resolveUser(request);
        if (user == null) {
            return RestResponse.error(401, "Authentication required");
        }
        try {
            List<SupportTicketAttachmentDto> uploaded = supportTicketService.uploadImageAttachments(
                    ticketId, files, user.getUserId(), user.getEmail(), null);
            return RestResponse.success("Images uploaded successfully.", uploaded);
        } catch (SecurityException e) {
            return RestResponse.error(403, e.getMessage());
        } catch (IllegalArgumentException e) {
            return RestResponse.error(400, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to upload support attachments for ticket {}", ticketId, e);
            return RestResponse.error(500, "Failed to upload images. Please try again.");
        }
    }

    private ResolvedUser resolveUser(HttpServletRequest request) {
        // 1. Direct gateway/service headers
        String headerUserId = request.getHeader("X-User-Id");
        String headerEmail = request.getHeader("X-User-Email");
        if (headerUserId != null && !headerUserId.isBlank()) {
            return new ResolvedUser(headerUserId.trim(), headerEmail != null ? headerEmail.trim() : null);
        }

        // 2. JWT token header (Bearer or Token)
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && !authHeader.isBlank()) {
            String token = null;
            if (authHeader.startsWith("Bearer ")) {
                token = authHeader.substring(7).trim();
            } else if (authHeader.startsWith("Token ")) {
                token = authHeader.substring(6).trim();
            }
            if (token != null && !token.isBlank()) {
                ResolvedUser jwtUser = parseJwtToken(token);
                if (jwtUser != null) {
                    return jwtUser;
                }
            }
        }

        return null;
    }

    private ResolvedUser parseJwtToken(String token) {
        try {
            String secret = supportProperties.getJwt().getSecret();
            Key key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
            Claims claims = Jwts.parser()
                    .setSigningKey(key)
                    .build()
                    .parseClaimsJws(token)
                    .getBody();

            String userId = claims.get("userId", String.class);
            if (userId == null) {
                userId = claims.get("id", String.class);
            }
            if (userId == null) {
                userId = claims.getSubject();
            }

            String email = claims.get("email", String.class);
            if (email == null) {
                email = claims.getSubject();
            }

            return new ResolvedUser(userId, email);
        } catch (Exception e) {
            log.debug("Could not parse JWT token: {}", e.getMessage());
            return null;
        }
    }

    @Data
    public static class ResolvedUser {
        private final String userId;
        private final String email;
    }
}
