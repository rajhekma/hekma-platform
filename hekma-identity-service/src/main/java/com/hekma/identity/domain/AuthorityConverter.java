package com.hekma.identity.domain;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import lombok.extern.slf4j.Slf4j;

/**
 * Stores {@link Authority} values by their stable key (e.g. {@code patient:read}).
 */
@Converter
@Slf4j
public class AuthorityConverter implements AttributeConverter<Authority, String> {

    @Override
    public String convertToDatabaseColumn(Authority authority) {
        return authority != null ? authority.key() : null;
    }

    @Override
    public Authority convertToEntityAttribute(String key) {
        if (key == null) {
            return null;
        }
        return Authority.fromKey(key).orElseGet(() -> {
            log.warn("Unknown or deprecated authority key in database: '{}'. Ignoring.", key);
            return null;
        });
    }
}
