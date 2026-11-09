package com.minicc.cloud.tasks;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

/**
 * Every failure leaves as a status and a reason, never as an empty array.
 *
 * <p>A 200 with {@code []} from a service whose database is missing would tell
 * a caller there is no task history at the exact moment none was read.
 */
@RestControllerAdvice
public class TaskFailureAdvice {

    public record ErrorBody(String error, String reason) {
    }

    @ExceptionHandler(TaskStoreUnavailableException.class)
    public ResponseEntity<ErrorBody> unavailable(TaskStoreUnavailableException exc) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody("tasks-db-unavailable", exc.getMessage()));
    }

    @ExceptionHandler(CorruptSnapshotException.class)
    public ResponseEntity<ErrorBody> corrupt(CorruptSnapshotException exc) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorBody("task-snapshot-corrupt", exc.getMessage()));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ErrorBody> refused(ResponseStatusException exc) {
        return ResponseEntity.status(exc.getStatusCode())
                .body(new ErrorBody("request-refused",
                        exc.getReason() == null ? exc.getMessage() : exc.getReason()));
    }
}
