package com.hekma.notification.support.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RestResponse<T> {

    private int code;
    private String type;
    private String message;
    private T data;

    public static <T> RestResponse<T> success(String message, T data) {
        return new RestResponse<>(200, "success", message, data);
    }

    public static <T> RestResponse<T> error(int code, String message) {
        return new RestResponse<>(code, "error", message, null);
    }
}
