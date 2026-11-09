package com.minicc.cloud.tasks;

import java.util.List;

/**
 * A list answer plus the statement that the caller asked for more than the
 * service is allowed to return. The body stays a JSON array, so the truncation
 * fact travels in a response header rather than beside an array it cannot join.
 */
public record TaskPage(List<TaskSummary> tasks, boolean truncated, int limit) {
}
