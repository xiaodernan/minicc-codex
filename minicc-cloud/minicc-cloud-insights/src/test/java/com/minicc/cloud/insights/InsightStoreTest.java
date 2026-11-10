package com.minicc.cloud.insights;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** The store answers exact totals and capped per-status counts, never guesses past the cap. */
class InsightStoreTest {

    @TempDir Path temp;

    @Test
    void totalAndPerStatusCountsAreExact() {
        Path db = InsightsFixture.database(temp);
        InsightsFixture.insert(db, "a", 100.0, "ws-a", InsightsFixture.snapshot("a", "completed"));
        InsightsFixture.insert(db, "b", 200.0, "ws-a", InsightsFixture.snapshot("b", "completed"));
        InsightsFixture.insert(db, "c", 300.0, "ws-b", InsightsFixture.snapshot("c", "queued"));

        InsightStore.Summary summary = store(db).summary(null);

        assertThat(summary.total()).isEqualTo(3);
        assertThat(summary.byStatus()).containsEntry("completed", 2L).containsEntry("queued", 1L);
        assertThat(summary.truncated()).isFalse();
        assertThat(summary.minCreatedAt()).isEqualTo(100.0);
        assertThat(summary.maxCreatedAt()).isEqualTo(300.0);
    }

    @Test
    void workspaceFilterScopesTotalsAndStatus() {
        Path db = InsightsFixture.database(temp);
        InsightsFixture.insert(db, "a", 100.0, "ws-a", InsightsFixture.snapshot("a", "running"));
        InsightsFixture.insert(db, "b", 200.0, "ws-a", InsightsFixture.snapshot("b", "failed"));
        InsightsFixture.insert(db, "c", 300.0, "ws-b", InsightsFixture.snapshot("c", "running"));

        InsightStore.Summary summary = store(db).summary("ws-a");

        assertThat(summary.total()).isEqualTo(2);
        assertThat(summary.byStatus()).containsEntry("running", 1L).containsEntry("failed", 1L);
    }

    @Test
    void perStatusScanStopsAtTheCapButTotalDoesNot() {
        Path db = InsightsFixture.database(temp);
        InsightsFixture.insert(db, "a", 100.0, "ws-a", InsightsFixture.snapshot("a", "completed"));
        InsightsFixture.insert(db, "b", 200.0, "ws-a", InsightsFixture.snapshot("b", "completed"));
        InsightsFixture.insert(db, "c", 300.0, "ws-a", InsightsFixture.snapshot("c", "queued"));

        InsightStore.Summary summary = store(db, 2).summary(null);

        assertThat(summary.total()).isEqualTo(3);  // COUNT(*) stays exact
        assertThat(summary.truncated()).isTrue(); // the scan hit the cap
        assertThat(summary.byStatus().values().stream().mapToLong(Long::longValue).sum())
                .isEqualTo(2);
    }

    @Test
    void aMissingDatabaseThrowsInsteadOfReportingEmpty() {
        Path missing = temp.resolve("nowhere").resolve("tasks.sqlite3");
        InsightStore store = store(missing, 1000, temp.resolve("audit.jsonl"));

        assertThatThrownBy(() -> store.summary(null))
                .isInstanceOf(InsightStoreUnavailableException.class);
    }

    @Test
    void aCorruptSnapshotFailsTheWholeSummary() {
        Path db = InsightsFixture.database(temp);
        InsightsFixture.insert(db, "broken", 400.0, "ws-a", "not json");

        assertThatThrownBy(() -> store(db).summary(null)).isInstanceOf(CorruptSnapshotException.class);
    }

    private static InsightStore store(Path db) {
        return store(db, 1000);
    }

    private static InsightStore store(Path db, int maxScanRows) {
        return store(db, maxScanRows, db.getParent().resolve("audit.jsonl"));
    }

    private static InsightStore store(Path db, int maxScanRows, Path audit) {
        try {
            if (!java.nio.file.Files.exists(audit)) {
                java.nio.file.Files.writeString(audit, "");
            }
        } catch (java.io.IOException exc) {
            throw new IllegalStateException(exc);
        }
        InsightsProperties properties =
                new InsightsProperties(db.toString(), audit.toString(), maxScanRows, 1000);
        return new InsightStore(properties);
    }
}
