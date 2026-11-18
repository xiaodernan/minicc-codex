package com.minicc.cloud.evidence;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Read side of the cache: absent is 503, corrupt is skipped-and-counted,
 * newest survives the cap, append is idempotent per run id.
 */
class EvidenceStoreTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @TempDir Path temp;

    @Test
    void aMissingFileThrows503Style() {
        EvidenceStore store = new EvidenceStore(EvidenceFixture.properties(temp.resolve("nowhere.jsonl")));

        assertThatThrownBy(store::readAll)
                .isInstanceOf(EvidenceStoreUnavailableException.class)
                .hasMessageContaining("nowhere.jsonl");
    }

    @Test
    void corruptLinesAreSkippedAndCounted() throws IOException {
        Path file = EvidenceFixture.storeFile(temp);
        EvidenceEntry good = EvidenceFixture.entry(1L, "2026-11-17T00:00:00Z", "success");
        Files.writeString(file,
                JSON.writeValueAsString(good) + "\n"
                        + "this is not json\n"
                        + "{\"run_id\":\"not-a-number\"}\n",
                StandardCharsets.UTF_8);

        EvidenceStore store = new EvidenceStore(EvidenceFixture.properties(file));

        EvidenceStore.Snapshot snapshot = store.readAll();
        assertThat(snapshot.entries()).hasSize(1);
        assertThat(snapshot.skippedLines()).isEqualTo(2);
    }

    @Test
    void appendIsIdempotentPerRunId() throws IOException {
        Path file = EvidenceFixture.storeFile(temp);
        EvidenceStore store = new EvidenceStore(EvidenceFixture.properties(file));
        EvidenceEntry entry = EvidenceFixture.entry(4242L, "2026-11-18T00:00:00Z", "success");

        Files.writeString(file, "", StandardCharsets.UTF_8);
        assertThat(store.appendIfAbsent(entry)).isTrue();
        assertThat(store.appendIfAbsent(entry)).isFalse();

        EvidenceStore.Snapshot snapshot = store.readAll();
        assertThat(snapshot.entries()).hasSize(1);
        assertThat(snapshot.entries().get(0).runId()).isEqualTo(4242L);
    }

    @Test
    void findReturnsTheEntryForOneRunId() throws IOException {
        Path file = EvidenceFixture.storeFile(temp);
        EvidenceStore store = new EvidenceStore(EvidenceFixture.properties(file));
        Files.writeString(file,
                JSON.writeValueAsString(EvidenceFixture.entry(11L, "2026-11-18T00:00:00Z", "failure")) + "\n",
                StandardCharsets.UTF_8);
        assertThat(store.find(11L)).isPresent();
        assertThat(store.find(12L)).isEmpty();
    }
}
