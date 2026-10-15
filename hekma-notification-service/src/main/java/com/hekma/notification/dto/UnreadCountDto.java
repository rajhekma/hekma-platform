package com.hekma.notification.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Unread notification count for a user")
public class UnreadCountDto {

    @Schema(description = "User ID")
    private String userId;

    @Schema(description = "Count of unread notifications")
    private long unreadCount;
}
