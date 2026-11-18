package com.minicc.cloud.evidence;

/** The JSONL cache exists for this service to read, but it could not be read or created. */
public class EvidenceStoreUnavailableException extends RuntimeException {

    public EvidenceStoreUnavailableException(String message) {
        super(message);
    }

    public EvidenceStoreUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
