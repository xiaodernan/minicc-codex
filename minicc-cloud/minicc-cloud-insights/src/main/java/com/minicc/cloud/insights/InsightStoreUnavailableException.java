package com.minicc.cloud.insights;

/** Raised when the read-only state store or audit log cannot be read at all. */
public class InsightStoreUnavailableException extends RuntimeException {

    public InsightStoreUnavailableException(String message) {
        super(message);
    }

    public InsightStoreUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
