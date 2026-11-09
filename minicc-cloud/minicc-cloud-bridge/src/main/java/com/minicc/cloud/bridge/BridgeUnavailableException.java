package com.minicc.cloud.bridge;

/**
 * Thrown when the boundary could not produce an answer.
 *
 * <p>The reason travels with the exception so a caller cannot answer "no changes"
 * on the strength of a read that never happened. Callers are expected to surface
 * {@link #reason()} to the client, not to log it and return an empty list.
 */
public class BridgeUnavailableException extends RuntimeException {

    private final String reason;

    public BridgeUnavailableException(String reason) {
        super(reason);
        this.reason = reason;
    }

    public BridgeUnavailableException(String reason, Throwable cause) {
        super(reason, cause);
        this.reason = reason;
    }

    public String reason() {
        return reason;
    }
}