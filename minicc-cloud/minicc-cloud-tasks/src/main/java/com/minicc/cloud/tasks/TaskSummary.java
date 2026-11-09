package com.minicc.cloud.tasks;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * A list entry with the snapshot's large fields left behind.
 *
 * <p>{@code payload} carries events and stream text that can be megabytes per
 * task; a list of twenty would ship all of it for two fields a caller reads.
 * The detail endpoint is where the whole snapshot lives.
 */
public record TaskSummary(
        @JsonProperty("task_id") String taskId,
        @JsonProperty("status") String status,
        @JsonProperty("created_at") double createdAt,
        @JsonProperty("workspace_path") String workspacePath,
        @JsonProperty("preview") String preview) {
}
