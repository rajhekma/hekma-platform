package com.hekma.notification.service;

import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class TemplateRenderer {

    public String render(String template, Map<String, Object> params) {
        if (template == null || params == null || params.isEmpty()) {
            return template;
        }

        String result = template;
        for (Map.Entry<String, Object> entry : params.entrySet()) {
            String placeholder = "{{" + entry.getKey() + "}}";
            String replacement = entry.getValue() != null ? String.valueOf(entry.getValue()) : "";
            result = result.replace(placeholder, replacement);
        }
        return result;
    }
}
