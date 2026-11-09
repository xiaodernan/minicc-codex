package com.minicc.cloud.tasks;

/**
 * The task database could not be read at all: the file is missing, cannot be
 * opened, or the query failed. Callers get a 503 with the path, never an empty
 * list that would read as "no tasks exist".
 */
public class TaskStoreUnavailableException extends RuntimeException {

    public TaskStoreUnavailableException(String message) {
        super(message);
    }

    public TaskStoreUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
