package com.minicc.cloud.tasks;

/** One row of {@code tasks}, exactly as the read-only statement returned it. */
public record TaskRow(String taskId, double createdAt, String workspacePath, String payload) {
}
