package com.minicc.cloud.tasks;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

/** One task with its complete, still-unparsed-by-the-caller snapshot. */
public record TaskDetail(
        @JsonProperty("task_id") String taskId,
        @JsonProperty("created_at") double createdAt,
        @JsonProperty("workspace_path") String workspacePath,
        @JsonProperty("payload") JsonNode payload) {
}
