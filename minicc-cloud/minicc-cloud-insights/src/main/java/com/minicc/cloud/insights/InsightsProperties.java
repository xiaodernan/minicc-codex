package com.minicc.cloud.insights;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Where the Python engine's state lives and how much one request may take.
 *
 * @param db            the SQLite file the engine writes; opened read-only
 * @param audit         the audit log; opened read-only, counted with a cap
 * @param maxScanRows   hard ceiling on {@code tasks} rows scanned to count
 *                      per-status; totals stay exact past this cap
 * @param maxAuditLines hard ceiling on audit lines counted per request
 */
@ConfigurationProperties(prefix = "minicc.cloud.insights")
public record InsightsProperties(String db, String audit, Integer maxScanRows, Integer maxAuditLines) {

    public InsightsProperties {
        if (db == null || db.isBlank()) {
            throw new IllegalStateException("minicc.cloud.insights.db must name the SQLite file to read");
        }
        if (audit == null || audit.isBlank()) {
            throw new IllegalStateException("minicc.cloud.insights.audit must name the audit log to read");
        }
        if (maxScanRows == null || maxScanRows < 1) {
            throw new IllegalStateException("minicc.cloud.insights.max-scan-rows must be a positive integer");
        }
        if (maxAuditLines == null || maxAuditLines < 1) {
            throw new IllegalStateException("minicc.cloud.insights.max-audit-lines must be a positive integer");
        }
    }
}
