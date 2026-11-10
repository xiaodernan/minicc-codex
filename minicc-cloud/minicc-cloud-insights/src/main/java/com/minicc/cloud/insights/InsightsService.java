package com.minicc.cloud.insights;

import org.springframework.stereotype.Service;

/** Composes the one aggregate summary - tasks from SQLite, lines from the audit log. */
@Service
public class InsightsService {

    private final InsightStore store;
    private final AuditReader audit;

    public InsightsService(InsightStore store, AuditReader audit) {
        this.store = store;
        this.audit = audit;
    }

    public SummaryResponse summarize(String workspace) {
        InsightStore.Summary tasks = store.summary(workspace);
        AuditReader.AuditSummary auditSummary = audit.read();
        String timestamp = java.time.Instant.now().toString();
        return new SummaryResponse(
                timestamp,
                new SummaryResponse.Tasks(
                        true,
                        tasks.total(),
                        tasks.byStatus(),
                        tasks.truncated(),
                        tasks.minCreatedAt(),
                        tasks.maxCreatedAt(),
                        workspace),
                new SummaryResponse.Audit(
                        auditSummary.present(),
                        auditSummary.lines(),
                        auditSummary.truncated(),
                        auditSummary.cappedAt()));
    }
}
