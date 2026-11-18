package com.minicc.cloud.evidence;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

/**
 * Orchestrates the evidence gate. Zero model calls, zero verdict prose: a run
 * is captured once per JVM (memo 10 min on {@code latest}), straight from the
 * cache if present, from GitHub exactly once if not.
 */
@Service
public class EvidenceService {

    private static final long LATEST_MEMO_MS = 10L * 60L * 1000L;

    private final EvidenceStore store;
    private final RunFetcher fetcher;
    private final ConcurrentHashMap<String, Memoized> memos = new ConcurrentHashMap<>();

    public EvidenceService(EvidenceStore store, RunFetcher fetcher) {
        this.store = store;
        this.fetcher = fetcher;
    }

    /** {@code latest=1}: the freshest run this host has ever captured, or an honest blank. */
    public EvidenceResponse latest() {
        return memoized("latest", () -> {
            EvidenceStore.Snapshot snapshot = store.readAll();
            Optional<EvidenceEntry> latest = snapshot.entries().stream()
                    .max(java.util.Comparator.comparing(EvidenceEntry::startedAt,
                            java.util.Comparator.nullsFirst(String::compareTo)));
            return response(snapshot, latest.orElse(null));
        });
    }

    /** {@code run_id=N}: cache-hit answers directly; a cache-miss backfills once. */
    public EvidenceResponse forRun(long runId) {
        Optional<EvidenceEntry> cached = store.find(runId);
        if (cached.isPresent()) {
            EvidenceStore.Snapshot snapshot = store.readAll();
            return response(snapshot, cached.get());
        }
        EvidenceEntry fresh = fetcher.fetch(runId);
        store.appendIfAbsent(fresh);
        EvidenceStore.Snapshot snapshot = store.readAll();
        return response(snapshot, fresh);
    }

    private EvidenceResponse memoized(String key, java.util.function.Supplier<EvidenceResponse> producer) {
        long now = System.currentTimeMillis();
        Memoized hit = memos.get(key);
        if (hit != null && now - hit.at < LATEST_MEMO_MS) {
            return hit.value;
        }
        EvidenceResponse value = producer.get();
        memos.put(key, new Memoized(now, value));
        return value;
    }

    private static EvidenceResponse response(EvidenceStore.Snapshot snapshot, EvidenceEntry latest) {
        List<EvidenceEntry> entries = snapshot.entries();
        if (entries.isEmpty()) {
            return new EvidenceResponse(false, Instant.now().toString(), 0,
                    snapshot.skippedLines(), "no evidence recorded yet", null, List.of());
        }
        return new EvidenceResponse(true, Instant.now().toString(), entries.size(),
                snapshot.skippedLines(), null, latest, entries);
    }

    private record Memoized(long at, EvidenceResponse value) {
    }
}
