package com.minicc.cloud.insights;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Instant;
import org.springframework.stereotype.Component;

/**
 * Disk usage view of the engine's {@code .minicc/} directory, read-only.
 *
 * <p>The "how much data are we holding" answer that `/api/insights/summary`
 * does not give: the SQLite file size, the number of session artefacts, and
 * remaining volume capacity, without touching a single byte of contents.
 */
@Component
public class DiskProbe {

    private final Path stateDir;
    private final Path databaseFile;

    public DiskProbe(InsightsProperties properties) {
        this.databaseFile = Path.of(properties.db());
        this.stateDir = databaseFile.getParent() != null ? databaseFile.getParent() : Path.of(".");
    }

    public DiskSummary probe() {
        boolean statePresent = Files.isDirectory(stateDir);
        boolean dbPresent = Files.isRegularFile(databaseFile);
        long bytes = 0L;
        long fileCount = 0L;
        long directoryCount = 0L;
        if (statePresent) {
            try (var stream = Files.walk(stateDir)) {
                for (Path p : (Iterable<Path>) stream::iterator) {
                    try {
                        boolean isDir = Files.isDirectory(p, LinkOption.NOFOLLOW_LINKS);
                        if (isDir) {
                            directoryCount++;
                        } else if (Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS)) {
                            fileCount++;
                            bytes += Files.size(p);
                        }
                    } catch (IOException ignored) {
                        fileCount++;
                    }
                }
            } catch (IOException ignored) {
            }
        }

        long freeBytes = Long.MIN_VALUE;
        String fileStore = null;
        try {
            if (statePresent) {
                var store = Files.getFileStore(stateDir);
                freeBytes = store.getUsableSpace();
                fileStore = store.name();
            }
        } catch (IOException ignored) {
        }

        return new DiskSummary(
                Instant.now().toString(),
                statePresent,
                new DiskSummary.Database(dbPresent, databaseFile.toString(), safeSize(databaseFile)),
                new DiskSummary.State(stateDir.toString(), fileCount, directoryCount, bytes),
                new DiskSummary.Volume(freeBytes, fileStore));
    }

    private static long safeSize(Path p) {
        try {
            return Files.size(p);
        } catch (IOException e) {
            return -1L;
        }
    }

    public record DiskSummary(
            @com.fasterxml.jackson.annotation.JsonProperty("generated_at") String generatedAt,
            @com.fasterxml.jackson.annotation.JsonProperty("state_present") boolean statePresent,
            @com.fasterxml.jackson.annotation.JsonProperty("database") Database database,
            @com.fasterxml.jackson.annotation.JsonProperty("state") State state,
            @com.fasterxml.jackson.annotation.JsonProperty("volume") Volume volume) {

        public record Database(
                @com.fasterxml.jackson.annotation.JsonProperty("present") boolean present,
                @com.fasterxml.jackson.annotation.JsonProperty("path") String path,
                @com.fasterxml.jackson.annotation.JsonProperty("bytes") long bytes) {
        }

        public record State(
                @com.fasterxml.jackson.annotation.JsonProperty("path") String path,
                @com.fasterxml.jackson.annotation.JsonProperty("file_count") long fileCount,
                @com.fasterxml.jackson.annotation.JsonProperty("directory_count") long directoryCount,
                @com.fasterxml.jackson.annotation.JsonProperty("bytes") long bytes) {
        }

        public record Volume(
                @com.fasterxml.jackson.annotation.JsonProperty("free_bytes") long freeBytes,
                @com.fasterxml.jackson.annotation.JsonProperty("file_store") String fileStore) {
        }
    }
}
