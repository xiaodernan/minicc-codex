package com.minicc.cloud.insights;

/** Raised when the service registry (Eureka) cannot be read at all.
 *
 * <p>A 200 with zero services would tell the operator the fleet is empty at
 * the exact moment the registry is unreachable — the same lie this service
 * exists to prevent on the SQLite side. The gateway's fleet route answers
 * 503 with a reason instead.
 */
public class RegistryUnavailableException extends RuntimeException {

    public RegistryUnavailableException(String message) {
        super(message);
    }

    public RegistryUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
