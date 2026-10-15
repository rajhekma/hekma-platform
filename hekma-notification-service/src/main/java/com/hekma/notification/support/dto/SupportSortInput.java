package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportSortInput {
    private String field = "createdTs";
    private String direction = "DESC";
}
