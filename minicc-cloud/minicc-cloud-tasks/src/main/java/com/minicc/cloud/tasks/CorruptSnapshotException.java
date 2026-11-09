package com.minicc.cloud.tasks;

/**
 * A row exists but its snapshot is not JSON. That is a damaged record, not a
 * task with no fields, so it surfaces as a 500 naming the task instead of an
 * empty detail.
 */
public class CorruptSnapshotException extends RuntimeException {

    private final String taskId;

    public CorruptSnapshotException(String taskId, String detail) {
        super("快照损坏：task_id=" + taskId + " 的 payload 不是合法 JSON（" + detail + "）");
        this.taskId = taskId;
    }

    public String taskId() {
        return taskId;
    }
}
