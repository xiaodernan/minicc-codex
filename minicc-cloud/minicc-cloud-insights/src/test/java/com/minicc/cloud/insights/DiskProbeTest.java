package com.minicc.cloud.insights;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * The disk probe reports shape and bytes, never contents. Shape: a present state
 * with files and sub-directories must report the count and at least one file's
 * size; an absent state must report state_present=false and not crash.
 */
class DiskProbeTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @TempDir Path temp;

    private Path db;
    private Path audit;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(temp);
        db = temp.resolve("tasks.sqlite3");
        audit = temp.resolve("audit.jsonl");
        // A non-empty database file; contents do not matter for the probe.
        Files.writeString(db, "payload".repeat(40), StandardCharsets.UTF_8);
        Files.writeString(audit, "{\"e\":1}\n{\"e\":2}\n", StandardCharsets.UTF_8);

        // A nested artefact tree so the walk sees directories and files.
        Path sub = temp.resolve("sessions").resolve("s1");
        Files.createDirectories(sub);
        Files.writeString(sub.resolve("transcript.jsonl"), "x".repeat(120), StandardCharsets.UTF_8);
    }

    @Test
    void itReportsAPresentDatabaseAndAWalkOfState() throws Exception {
        MockMvc mvc = mvcFor(db, audit);

        JsonNode body = answer(mvc, get("/api/insights/disk"), 200);

        assertThat(body.get("state_present").asBoolean()).isTrue();
        assertThat(body.get("database").get("present").asBoolean()).isTrue();
        assertThat(body.get("database").get("bytes").asLong()).isGreaterThan(0);
        assertThat(body.get("state").get("directory_count").asLong()).isGreaterThanOrEqualTo(1);
        assertThat(body.get("state").get("file_count").asLong()).isGreaterThanOrEqualTo(2);
        assertThat(body.get("state").get("bytes").asLong()).isGreaterThanOrEqualTo(db.toFile().length());
        assertThat(body.get("volume").get("free_bytes").asLong()).isGreaterThanOrEqualTo(-1L);
        assertThat(body.get("generated_at").asText()).isNotBlank();
    }

    @Test
    void anAbsentStateDirectoryReportsFalse() throws Exception {
        Path missing = temp.resolve("nowhere").resolve("tasks.sqlite3");
        MockMvc mvc = mvcFor(missing, audit);

        JsonNode body = answer(mvc, get("/api/insights/disk"), 200);

        assertThat(body.get("state_present").asBoolean()).isFalse();
        assertThat(body.get("database").get("present").asBoolean()).isFalse();
        assertThat(body.get("state").get("file_count").asLong()).isZero();
    }

    private static MockMvc mvcFor(Path database, Path auditFile) {
        InsightsProperties properties =
                new InsightsProperties(database.toString(), auditFile.toString(), 1000, 100);
        DiskProbe probe = new DiskProbe(properties);
        InsightsService service =
                new InsightsService(new InsightStore(properties), new AuditReader(properties));
        return MockMvcBuilders.standaloneSetup(new InsightsController(service, probe))
                .setControllerAdvice(new InsightsFailureAdvice())
                .build();
    }

    private JsonNode answer(
            MockMvc mvc,
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request,
            int expectedStatus)
            throws Exception {
        MvcResult result = mvc.perform(request)
                .andExpect(status().is(expectedStatus))
                .andReturn();
        return JSON.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }
}
