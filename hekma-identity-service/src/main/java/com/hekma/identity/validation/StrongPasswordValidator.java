package com.hekma.identity.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

/**
 * Password policy: 8–128 characters, at least one uppercase letter, one lowercase letter,
 * one digit and one special character, and no leading or trailing whitespace.
 * A null value is left to {@code @NotBlank}.
 */
public class StrongPasswordValidator implements ConstraintValidator<StrongPassword, String> {

    public static final int MIN_LENGTH = 8;
    public static final int MAX_LENGTH = 128;
    public static final String POLICY_MESSAGE = "Password must be 8-128 characters and contain an uppercase letter, "
            + "a lowercase letter, a digit and a special character, with no leading or trailing spaces";

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) {
            return true;
        }
        return isStrong(value);
    }

    public static boolean isStrong(String value) {
        if (value.length() < MIN_LENGTH || value.length() > MAX_LENGTH || !value.equals(value.strip())) {
            return false;
        }
        boolean upper = false, lower = false, digit = false, special = false;
        for (char c : value.toCharArray()) {
            if (Character.isUpperCase(c)) {
                upper = true;
            } else if (Character.isLowerCase(c)) {
                lower = true;
            } else if (Character.isDigit(c)) {
                digit = true;
            } else if (!Character.isWhitespace(c)) {
                special = true;
            }
        }
        return upper && lower && digit && special;
    }
}
