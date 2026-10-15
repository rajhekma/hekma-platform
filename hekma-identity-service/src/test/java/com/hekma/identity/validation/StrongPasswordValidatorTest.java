package com.hekma.identity.validation;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;

class StrongPasswordValidatorTest {

    private final StrongPasswordValidator validator = new StrongPasswordValidator();

    @ParameterizedTest
    @ValueSource(strings = {"Password123!", "Aa1!aaaa", "Long-Pass phrase 2026"})
    @DisplayName("Passwords meeting the policy are accepted")
    void validPasswords_accepted(String password) {
        assertThat(validator.isValid(password, null)).isTrue();
    }

    @ParameterizedTest
    @ValueSource(strings = {"Aa1!aaa", "password123!", "PASSWORD123!", "Password!!!", "Password123", " Password123!", "Password123! "})
    @DisplayName("Short passwords, missing character classes and edge whitespace are rejected")
    void weakPasswords_rejected(String password) {
        assertThat(validator.isValid(password, null)).isFalse();
    }

    @org.junit.jupiter.api.Test
    @DisplayName("Passwords longer than 128 characters are rejected; null is left to @NotBlank")
    void lengthLimitAndNull() {
        assertThat(validator.isValid("Aa1!" + "a".repeat(125), null)).isFalse();
        assertThat(validator.isValid(null, null)).isTrue();
    }
}
