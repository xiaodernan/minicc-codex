package com.minicc.cloud.insights;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** The audit side of the summary: a missing log is a fact, an unreadable one is a failure. */
class AuditReaderTest {

    @TempDir Path temp;

    @Test
    void aMissingAuditIsPresentFalseWithZeroLines() {
        Path audit = temp.resolve("no-such-file").resolve("audit.jsonl");
        InsightsProperties properties = new InsightsProperties(db(), audit.toString(), 1000, 100);

        AuditReader.AuditSummary summary = new AuditReader(properties).read();

        assertThat(summary.present()).isFalse();
        assertThat(summary.lines()).isZero();
        assertThat(summary.truncated()).isFalse();
    }

    @Test
    void linesAreCountedExactly() {
        Path audit = InsightsFixture.auditLog(temp, "{\"a\":1}", "{\"a\":2}", "{\"a\":3}");
        InsightsProperties properties = new InsightsProperties(db(), audit.toString(), 1000, 100);

        assertThat(new AuditReader(properties).read().lines()).isEqualTo(3);
    }

    @Test
    void theCapStopsCountingAndSaysTruncated() {
        Path audit = InsightsFixture.auditLog(temp, "1", "2", "3", "4", "5");
        InsightsProperties properties = new InsightsProperties(db(), audit.toString(), 1000, 2);

        AuditReader.AuditSummary summary = new AuditReader(properties).read();

        assertThat(summary.present()).isTrue();
        assertThat(summary.lines()).isEqualTo(2);
        assertThat(summary.truncated()).isTrue();
        assertThat(summary.cappedAt()).isEqualTo(2);
    }

    private static String db() {
        return java.nio.file.Paths.get("unused-tasks.sqlite3").toAbsolutePath().toString();
    }
}
