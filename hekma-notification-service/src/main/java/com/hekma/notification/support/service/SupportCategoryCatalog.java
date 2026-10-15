package com.hekma.notification.support.service;

import com.hekma.notification.support.dto.SupportCategoryOptionDto;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public final class SupportCategoryCatalog {

    public static final String LOGIN_ISSUE = "LOGIN_ISSUE";
    public static final String PASSWORD_MFA_ISSUE = "PASSWORD_MFA_ISSUE";
    public static final String MEDICATION_REMINDER = "MEDICATION_REMINDER";
    public static final String APP_CRASH = "APP_CRASH";
    public static final String SYNC_ISSUE = "SYNC_ISSUE";
    public static final String DEVICE_ISSUE = "DEVICE_ISSUE";
    public static final String STUDY_ACCESS = "STUDY_ACCESS";
    public static final String OTHER_INQUIRIES = "OTHER_INQUIRIES";

    private static final List<CategoryDef> CATEGORIES = Arrays.asList(
            new CategoryDef(LOGIN_ISSUE, "Login Issue"),
            new CategoryDef(PASSWORD_MFA_ISSUE, "Password / MFA Issue"),
            new CategoryDef(MEDICATION_REMINDER, "Medication Reminder"),
            new CategoryDef(APP_CRASH, "App Crash"),
            new CategoryDef(SYNC_ISSUE, "Sync Issue"),
            new CategoryDef(DEVICE_ISSUE, "Device Issue"),
            new CategoryDef(STUDY_ACCESS, "Study Access"),
            new CategoryDef(OTHER_INQUIRIES, "Other inquiries")
    );

    private SupportCategoryCatalog() {
    }

    public static List<SupportCategoryOptionDto> listCategories() {
        return CATEGORIES.stream()
                .map(c -> new SupportCategoryOptionDto(c.code, c.label))
                .collect(Collectors.toList());
    }

    public static boolean isValid(String code) {
        if (code == null || code.trim().isEmpty()) {
            return false;
        }
        String normalized = normalizeCode(code);
        return CATEGORIES.stream().anyMatch(c -> c.code.equals(normalized));
    }

    public static String normalizeCode(String code) {
        if (code == null) {
            return OTHER_INQUIRIES;
        }
        String normalized = code.trim().toUpperCase(Locale.ROOT).replace(' ', '_').replace('/', '_');
        if ("OTHER".equals(normalized) || "GENERAL".equals(normalized)) {
            return OTHER_INQUIRIES;
        }
        for (CategoryDef def : CATEGORIES) {
            if (def.code.equals(normalized) || def.label.equalsIgnoreCase(code.trim())) {
                return def.code;
            }
        }
        return normalized;
    }

    public static String labelFor(String code) {
        String normalized = normalizeCode(code);
        for (CategoryDef def : CATEGORIES) {
            if (def.code.equals(normalized)) {
                return def.label;
            }
        }
        return code;
    }

    public static String defaultSubjectFor(String code) {
        return labelFor(code);
    }

    public static String toDisplayStatus(String status) {
        if (status == null) {
            return null;
        }
        String normalized = status.toUpperCase(Locale.ROOT);
        if ("SUBMITTED".equals(normalized)) {
            normalized = "RECEIVED";
        }
        switch (normalized) {
            case "RECEIVED":
                return "Received";
            case "DRAFT":
                return "Draft";
            case "ASSIGNED":
                return "Assigned";
            case "IN_REVIEW":
                return "In Review";
            case "AWAITING_USER_RESPONSE":
                return "Awaiting Your Response";
            case "RESOLVED":
                return "Resolved";
            case "CLOSED":
                return "Closed";
            case "ESCALATED":
                return "Escalated";
            default:
                return normalized.replace('_', ' ');
        }
    }

    public static String normalizeStatus(String status) {
        if (status == null) {
            return null;
        }
        String normalized = status.trim().toUpperCase(Locale.ROOT);
        if ("SUBMITTED".equals(normalized)) {
            return "RECEIVED";
        }
        return normalized;
    }

    private static final class CategoryDef {
        private final String code;
        private final String label;

        private CategoryDef(String code, String label) {
            this.code = code;
            this.label = label;
        }
    }
}
