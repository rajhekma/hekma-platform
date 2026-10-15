package com.hekma.notification.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Response details for a multi-channel broadcast notification")
public class BroadcastNotificationResponse {

    @Schema(description = "Total number of channels dispatched")
    private int totalDispatched;

    @Schema(description = "Individual dispatch results for each channel")
    private List<NotificationResponse> results;
}
