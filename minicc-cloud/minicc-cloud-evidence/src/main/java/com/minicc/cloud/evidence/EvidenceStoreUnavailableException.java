package com.minicc.cloud.evidence;

/** The JSONL cache exists for this service to read, but it could not be read or created. */
public class EvidenceStoreUnavailableException extends RuntimeException {

    private final boolean missing;

    public EvidenceStoreUnavailableException(String message) {
        this(message, false, null);
    }

    public EvidenceStoreUnavailableException(String message, Throwable cause) {
        this(message, false, cause);
    }

    private EvidenceStoreUnavailableException(String message, boolean missing, Throwable cause) {
        super(message, cause);
        this.missing = missing;
    }

    /** true when the file simply does not exist yet (self-heal allowed), false when it exists but cannot be read/written. */
    public boolean isMissing() {
        return missing;
    }

    /** Factory for the "file does not exist yet" case - the one self-healing path. */
    public static EvidenceStoreUnavailableException missing(String message) {
        return new EvidenceStoreUnavailableException(message, true, null);
    }
}
