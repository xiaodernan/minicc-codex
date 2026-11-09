package com.minicc.cloud.inspector;

import com.minicc.cloud.bridge.BridgeUnavailableException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

/**
 * Every failure leaves as a status and a reason, never as an empty payload.
 *
 * <p>A 200 with {@code {"files": [], "total_files": 0}} after the Python child
 * died would be the exact defect the bridge was written to prevent, one layer
 * up: the HTTP client would render a clean workspace it was never told about.
 */
@RestControllerAdvice
public class BridgeFailureAdvice {

    public record ErrorBody(String error, String reason) {
    }

    @ExceptionHandler(BridgeUnavailableException.class)
    public ResponseEntity<ErrorBody> unavailable(BridgeUnavailableException exc) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody("minicc-unavailable", exc.reason()));
    }

    @ExceptionHandler(CallNotPermittedException.class)
    public ResponseEntity<ErrorBody> circuitOpen(CallNotPermittedException exc) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody("minicc-circuit-open",
                        "the minicc circuit breaker is open after repeated read failures; "
                                + "no inspection was attempted, so nothing is known about this workspace"));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ErrorBody> refused(ResponseStatusException exc) {
        return ResponseEntity.status(exc.getStatusCode())
                .body(new ErrorBody("workspace-refused",
                        exc.getReason() == null ? exc.getMessage() : exc.getReason()));
    }
}