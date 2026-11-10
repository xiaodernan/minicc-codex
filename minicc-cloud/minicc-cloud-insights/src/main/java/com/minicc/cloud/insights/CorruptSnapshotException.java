package com.minicc.cloud.insights;

/** A task snapshot that is not readable as JSON in the shape the engine writes. */
public class CorruptSnapshotException extends RuntimeException {

    public CorruptSnapshotException(String taskId, String detail) {
        super("任务快照损坏：" + taskId + "（" + detail + "）");
    }
}
