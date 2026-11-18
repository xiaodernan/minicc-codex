package com.minicc.cloud.evidence;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * The JSONL cache this service owns and only this service writes.
 *
 * <p>Two rules hold everywhere: an unreadable or unwritable file is reported
 * as {@link EvidenceStoreUnavailableException}, and a corrupt line is skipped
 * and counted - never fatal, never silently repaired. Reads never cap below
 * the configured ceiling; the newest line past the cap wins.
 */
@Component
public class EvidenceStore {

    private static final ObjectMapper JSON = new ObjectMapper();

    private final Path path;
    private final int maxEntries;

    public EvidenceStore(EvidenceProperties properties) {
        this.path = Path.of(properties.store()).toAbsolutePath().normalize();
        this.maxEntries = properties.maxEntries();
    }

    public Path path() {
        return path;
    }

    /** Snapshot of everything retained; corrupt lines counted, never thrown on. */
    public Snapshot readAll() {
        if (!Files.isRegularFile(path)) {
            throw new EvidenceStoreUnavailableException("evidence store does not exist: " + path);
        }
        List<EvidenceEntry> entries = new ArrayList<>();
        long skipped = 0;
        try (var stream = Files.lines(path, StandardCharsets.UTF_8)) {
            var iterator = stream.iterator();
            while (iterator.hasNext()) {
                String raw = iterator.next().trim();
                if (raw.isEmpty()) {
                    continue;
                }
                try {
                    entries.add(JSON.readValue(raw, EvidenceEntry.class));
                } catch (IOException | UncheckedIOException exc) {
                    skipped++;
                }
            }
        } catch (IOException exc) {
            throw new EvidenceStoreUnavailableException("evidence store unreadable: " + path, exc);
        }
        // Keep the tail; the cap says "the count is a lower bound", never a lie.
        if (entries.size() > maxEntries) {
            entries = new ArrayList<>(entries.subList(entries.size() - maxEntries, entries.size()));
        }
        return new Snapshot(List.copyOf(entries), skipped);
    }

    /** Idempotent per runId: a second capture of the same run is a no-op. */
    public boolean appendIfAbsent(EvidenceEntry entry) {
        Snapshot snapshot = readAll();
        for (EvidenceEntry existing : snapshot.entries()) {
            if (existing.runId() == entry.runId()) {
                return false;
            }
        }
        try {
            Path parent = path.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            String line = JSON.writeValueAsString(entry);
            Files.writeString(path, line + "\n", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            return true;
        } catch (IOException exc) {
            throw new EvidenceStoreUnavailableException("evidence store not writable: " + path, exc);
        }
    }

    /** The freshest entry with this run id, if any. */
    public Optional<EvidenceEntry> find(long runId) {
        return readAll().entries().stream()
                .filter(entry -> entry.runId() == runId)
                .reduce((first, second) -> second);
    }

    public record Snapshot(List<EvidenceEntry> entries, long skippedLines) {
    }
}
