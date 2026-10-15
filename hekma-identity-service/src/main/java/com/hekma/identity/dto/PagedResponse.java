package com.hekma.identity.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.domain.Page;

import java.util.Collections;
import java.util.List;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Standard paginated response wrapper")
public class PagedResponse<T> {

    @Schema(description = "List of items in the current page")
    @Builder.Default
    private List<T> content = Collections.emptyList();

    @Schema(description = "Current page index (0-based)", example = "0")
    private int page;

    @Schema(description = "Configured page size", example = "20")
    private int size;

    @Schema(description = "Total number of elements across all pages", example = "42")
    private long totalElements;

    @Schema(description = "Total number of pages", example = "3")
    private int totalPages;

    @Schema(description = "Whether this is the first page", example = "true")
    private boolean first;

    @Schema(description = "Whether this is the last page", example = "false")
    private boolean last;

    @Schema(description = "Whether the current page has no elements", example = "false")
    private boolean empty;

    public static <T> PagedResponse<T> of(Page<T> page) {
        if (page == null) {
            return PagedResponse.<T>builder()
                    .content(Collections.emptyList())
                    .page(0)
                    .size(0)
                    .totalElements(0)
                    .totalPages(0)
                    .first(true)
                    .last(true)
                    .empty(true)
                    .build();
        }
        return PagedResponse.<T>builder()
                .content(page.getContent())
                .page(page.getNumber())
                .size(page.getSize())
                .totalElements(page.getTotalElements())
                .totalPages(page.getTotalPages())
                .first(page.isFirst())
                .last(page.isLast())
                .empty(page.isEmpty())
                .build();
    }
}
