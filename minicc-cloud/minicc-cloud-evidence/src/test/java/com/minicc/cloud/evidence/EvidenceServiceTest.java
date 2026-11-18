package com.minicc.cloud.evidence;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * The orchestration law: cache-hit answers never reach GitHub, a cache-miss backfills
 * exactly once, latest-of-empty is an honest blank, and a missing file is never a
 * silent success.
 */
class EvidenceServiceTest {

    @TempDir Path temp;

    @Test
    void cacheHitAnswersWithoutFetching() throws IOException {
        Path file = EvidenceFixture.storeFile(temp);
        Files.writeString(file, "", StandardCharsets.UTF_8);
        EvidenceEntry canned = EvidenceFixture.entry(7331L, "2026-11-18T00:00:00Z", "failure");
        EvidenceFixture.CountingFetcher fetcher = new EvidenceFixture.CountingFetcher(canned);
        EvidenceService service = new EvidenceService(
                new EvidenceStore(EvidenceFixture.properties(file)), fetcher);

        EvidenceResponse first = service.forRun(7331L);
        assertThat(first.present()).isTrue();
        assertThat(fetcher.calls()).isEqualTo(1);

        EvidenceResponse second = service.forRun(7331L);
        assertThat(second.present()).isTrue();
        assertThat(second.entries()).allMatch(entry -> entry.runId() == 7331L);
        assertThat(fetcher.calls()).as("a cache-hit must not call GitHub again").isEqualTo(1);
    }

    @Test
    void latestOfAnEmptyStoreIsHonestNotWrong() throws IOException {
        Path file = EvidenceFixture.storeFile(temp);
        Files.writeString(file, "", StandardCharsets.UTF_8);
        EvidenceService service = new EvidenceService(
                new EvidenceStore(EvidenceFixture.properties(file)),
                new EvidenceFixture.CountingFetcher(EvidenceFixture.entry(1L, "2026-11-18T00:00:00Z", "success")));

        EvidenceResponse response = service.latest();
        assertThat(response.present()).isFalse();
        assertThat(response.reason()).contains("no evidence");
        assertThat(response.count()).isZero();
    }

    @Test
    void latestOfAMissingFileThrowsStoreUnavailable() {
        EvidenceService service = new EvidenceService(
                new EvidenceStore(EvidenceFixture.properties(temp.resolve("missing.jsonl"))),
                new EvidenceFixture.CountingFetcher(EvidenceFixture.entry(1L, "2026-11-18T00:00:00Z", "success")));

        assertThatThrownBy(service::latest)
                .isInstanceOf(EvidenceStoreUnavailableException.class);
    }

    @Test
    void runBackfillsAgainstAMissingStoreAndCreatesIt() {
        Path missing = temp.resolve("fresh-store.jsonl");
        Path parent = missing.getParent();
        assertThat(parent).exists();
        EvidenceFixture.CountingFetcher fetcher =
                new EvidenceFixture.CountingFetcher(EvidenceFixture.entry(8100L, "2026-11-18T00:00:00Z", "failure"));
        EvidenceService service = new EvidenceService(
                new EvidenceStore(EvidenceFixture.properties(missing)), fetcher);

        EvidenceResponse response = service.forRun(8100L);

        assertThat(response.present()).isTrue();
        assertThat(response.latest().runId()).isEqualTo(8100L);
        assertThat(missing).exists();
        assertThat(fetcher.calls()).isEqualTo(1);
        EvidenceStore reopened = new EvidenceStore(EvidenceFixture.properties(missing));
        assertThat(reopened.find(8100L)).isPresent();
    }
}
