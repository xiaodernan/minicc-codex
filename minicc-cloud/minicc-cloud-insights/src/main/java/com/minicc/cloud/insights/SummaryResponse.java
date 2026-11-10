package com.minicc.cloud.insights;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

/** One JSON answer: the engine's task totals + audit size, never the raw rows or lines. */
public record SummaryResponse(
        @JsonProperty("generated_at") String generatedAt,
        @JsonProperty("tasks") Tasks tasks,
        @JsonProperty("audit") Audit audit) {

    public record Tasks(
            @JsonProperty("present") boolean present,
            @JsonProperty("total") long total,
            @JsonProperty("by_status") Map<String, Long> byStatus,
            @JsonProperty("scan_truncated") boolean scanTruncated,
            @JsonProperty("min_created_at") Double minCreatedAt,
            @JsonProperty("max_created_at") Double maxCreatedAt,
            @JsonProperty("workspace") String workspace) {
    }

    public record Audit(
            @JsonProperty("present") boolean present,
            @JsonProperty("lines") long lines,
            @JsonProperty("truncated") boolean truncated,
            @JsonProperty("capped_at") int cappedAt) {
    }
}
