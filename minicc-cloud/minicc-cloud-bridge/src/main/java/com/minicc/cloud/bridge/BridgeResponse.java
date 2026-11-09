package com.minicc.cloud.bridge;

import java.time.Duration;

/**
 * What one run of the minicc process actually answered.
 *
 * <p>The three ways a read can fail are kept apart on purpose. A non-zero exit is
 * the program reporting a failure; a timeout is the program never reporting at
 * all; a transport error is the boundary itself failing to start or to drain a
 * pipe. Collapsing any of them into "exit 0, empty stdout" is the defect this
 * whole package exists to prevent - the Python side spent eight batches learning
 * that {@code total_files: 0} from a failed read is not "nothing changed".
 *
 * @param exitCode       the child's exit status, or -1 when it never produced one
 * @param stdout         everything the child wrote to stdout, decoded as UTF-8
 * @param stderr         everything the child wrote to stderr, decoded as UTF-8
 * @param timedOut       true when the child was destroyed for exceeding the budget
 * @param transportError non-null when the process could not be started or a pipe
 *                       could not be read whole; carries which half and why
 * @param elapsed        wall time spent, or the budget on a timeout
 */
public record BridgeResponse(
        int exitCode,
        String stdout,
        String stderr,
        boolean timedOut,
        String transportError,
        Duration elapsed) {

    public BridgeResponse {
        // Every failure leaves through failureReason(), which quotes stderr, so
        // scrubbing in this constructor is the single choke point for both the
        // HTTP body and the log line. stdout is left alone: it is data the
        // caller parses, not a diagnostic, and rewriting it would corrupt it.
        stderr = SecretRedactor.redact(stderr);
        transportError = SecretRedactor.redact(transportError);
    }

    public boolean succeeded() {
        return transportError == null && !timedOut && exitCode == 0;
    }

    /** Null on success; never null and never empty on any kind of failure. */
    public String failureReason() {
        if (succeeded()) {
            return null;
        }
        if (transportError != null) {
            return transportError;
        }
        if (timedOut) {
            return "the minicc process did not finish within " + elapsed + " and was destroyed";
        }
        String detail = stderr == null ? "" : stderr.strip();
        if (detail.isEmpty()) {
            detail = "(the process wrote nothing to stderr)";
        }
        return "the minicc process exited " + exitCode + ": " + detail;
    }
}