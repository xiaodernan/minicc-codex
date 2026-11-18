package com.minicc.cloud.evidence;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

/** Deterministic fixtures for the evidence gate; no network, no tokens. */
final class EvidenceFixture {

    private EvidenceFixture() {
    }

    static EvidenceProperties properties(Path store) {
        return new EvidenceProperties(
                store.toString(),
                "https://api.example.invalid",
                "someone",
                "some-repo",
                "",                       // token: deliberately blank in every test
                50,
                20,
                4096,
                1000L,
                1000L);
    }

    static EvidenceEntry entry(long runId, String startedAt, String conclusion) {
        return new EvidenceEntry(
                runId,
                "abc1234",
                "CI",
                "completed",
                conclusion,
                "job-1",
                "Python tests",
                "pytest",
                startedAt,
                List.of("line 1", "line 2", "FAILED: boom"),
                "2026-11-18T00:00:00Z");
    }

    static Path storeFile(Path dir) {
        try {
            Files.createDirectories(dir);
            return dir.resolve("evidence.jsonl");
        } catch (IOException exc) {
            throw new UncheckedIOException(exc);
        }
    }

    /** Counting fake: hands out canned results, records how often it was consulted. */
    static final class CountingFetcher implements RunFetcher {
        private final EvidenceEntry canned;
        private final AtomicInteger calls = new AtomicInteger();

        CountingFetcher(EvidenceEntry canned) {
            this.canned = canned;
        }

        int calls() {
            return calls.get();
        }

        @Override
        public EvidenceEntry fetch(long runId) {
            calls.incrementAndGet();
            return canned;
        }
    }

    static final class ExplodingFetcher implements RunFetcher {
        @Override
        public EvidenceEntry fetch(long runId) {
            throw new EvidenceBackfillException("boom for run " + runId);
        }
    }
}
