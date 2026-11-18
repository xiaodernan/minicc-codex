package com.minicc.cloud.evidence;

/** The run was not already in the cache and the backfill failed; nothing was written. */
public class EvidenceBackfillException extends RuntimeException {

    public EvidenceBackfillException(String message) {
        super(message);
    }

    public EvidenceBackfillException(String message, Throwable cause) {
        super(message, cause);
    }
}
