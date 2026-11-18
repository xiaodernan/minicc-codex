package com.minicc.cloud.evidence;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

/**
 * Every failure leaves as a status and a reason, never as a false success and
 * never as an empty claim. A 200 saying "nothing happened" when the cache was
 * unreadable would be the exact lie this service exists to prevent.
 */
@RestControllerAdvice
public class EvidenceFailureAdvice {

    public record ErrorBody(boolean present, String error, String reason) {
    }

    @ExceptionHandler(EvidenceStoreUnavailableException.class)
    public ResponseEntity<ErrorBody> storeUnavailable(EvidenceStoreUnavailableException exc) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody(false, "evidence-store-unavailable", exc.getMessage()));
    }

    @ExceptionHandler(EvidenceBackfillException.class)
    public ResponseEntity<ErrorBody> backfillFailed(EvidenceBackfillException exc) {
        // A failed backfill is always "we know nothing", never "the run passed".
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody(false, "evidence-backfill-failed", exc.getMessage()));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ErrorBody> refused(ResponseStatusException exc) {
        return ResponseEntity.status(exc.getStatusCode())
                .body(new ErrorBody(false, "request-refused",
                        exc.getReason() == null ? exc.getMessage() : exc.getReason()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorBody> crashed(Exception exc) {
        // Last-resort truth: we are broken, not "empty". The reason carries the
        // exception class only - never its message (which may know a path or a token).
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorBody(false, "evidence-crashed", exc.getClass().getSimpleName()));
    }
}
