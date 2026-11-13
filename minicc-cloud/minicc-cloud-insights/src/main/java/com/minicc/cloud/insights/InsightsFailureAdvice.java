package com.minicc.cloud.insights;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

/**
 * Every failure leaves as a status and a reason, never as an empty summary.
 * A 200 claiming zero tasks at the moment the database was missing would be
 * the exact lie this service exists to prevent.
 */
@RestControllerAdvice
public class InsightsFailureAdvice {

    public record ErrorBody(String error, String reason) {
    }

    @ExceptionHandler(InsightStoreUnavailableException.class)
    public ResponseEntity<ErrorBody> unavailable(InsightStoreUnavailableException exc) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody("insights-store-unavailable", exc.getMessage()));
    }

    @ExceptionHandler(RegistryUnavailableException.class)
    public ResponseEntity<ErrorBody> registryUnavailable(RegistryUnavailableException exc) {
        // A blind registry is not an empty fleet - same rule as the store.
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody("registry-unavailable", exc.getMessage()));
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
