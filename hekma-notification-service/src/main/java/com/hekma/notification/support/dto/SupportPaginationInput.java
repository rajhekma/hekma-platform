package com.hekma.notification.support.dto;

import lombok.Data;

@Data
public class SupportPaginationInput {
    private Integer page = 0;
    private Integer pageSize = 20;
}
