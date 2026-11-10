package com.minicc.cloud.insights;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * The HTTP shape: one JSON object with {@code tasks} and {@code audit}
 * sub-objects, and failure statuses that cannot be mistaken for "no data".
 */
class InsightsControllerTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @TempDir Path temp;

    private Path db;
    private Path audit;
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        db = InsightsFixture.database(temp);
        audit = InsightsFixture.auditLog(temp, "{\"e\":1}", "{\"e\":2}");
        InsightsFixture.insert(db, "old", 100.0, "ws-a", InsightsFixture.snapshot("old", "completed"));
        InsightsFixture.insert(db, "new", 300.0, "ws-a", InsightsFixture.snapshot("new", "queued"));
        mvc = mvcFor(db, audit);
    }

    @Test
    void summaryReportsTotalsStatusBreakdownAndAuditLines() throws Exception {
        JsonNode body = answer(get("/api/insights/summary"), 200);

        assertThat(body.get("tasks").get("total").asLong()).isEqualTo(2);
        assertThat(body.get("tasks").get("by_status").get("completed").asLong()).isEqualTo(1);
        assertThat(body.get("tasks").get("by_status").get("queued").asLong()).isEqualTo(1);
        assertThat(body.get("tasks").get("min_created_at").asDouble()).isEqualTo(100.0);
        assertThat(body.get("tasks").get("max_created_at").asDouble()).isEqualTo(300.0);
        assertThat(body.get("tasks").get("workspace").isNull()).isTrue();
        assertThat(body.get("audit").get("present").asBoolean()).isTrue();
        assertThat(body.get("audit").get("lines").asLong()).isEqualTo(2);
        assertThat(body.get("generated_at").asText()).isNotBlank();
    }

    @Test
    void workspaceFilterRestrictsTheTasksSide() throws Exception {
        InsightsFixture.insert(db, "other", 400.0, "ws-b", InsightsFixture.snapshot("other", "running"));

        JsonNode body = answer(get("/api/insights/summary").param("workspace", "ws-b"), 200);

        assertThat(body.get("tasks").get("total").asLong()).isEqualTo(1);
        assertThat(body.get("tasks").get("workspace").asText()).isEqualTo("ws-b");
    }

    @Test
    void aMissingDatabaseIsA503NeverAnEmptySummary() throws Exception {
        Path missingDb = temp.resolve("nowhere").resolve("tasks.sqlite3");
        MockMvc absent = mvcFor(missingDb, audit);

        MvcResult result = absent.perform(get("/api/insights/summary"))
                .andExpect(status().isServiceUnavailable())
                .andReturn();
        JsonNode body = JSON.readTree(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8));

        assertThat(body.get("error").asText()).isEqualTo("insights-store-unavailable");
        assertThat(result.getResponse().getContentAsString(StandardCharsets.UTF_8))
                .doesNotStartWith("{\"tasks\":");
    }

    @Test
    void aCorruptSnapshotIsA500NamingTheBrokenId() throws Exception {
        InsightsFixture.insert(db, "broken", 500.0, "ws-a", "not json");

        JsonNode body = answer(get("/api/insights/summary"), 500);

        assertThat(body.get("error").asText()).isEqualTo("task-snapshot-corrupt");
        assertThat(body.get("reason").asText()).contains("broken");
    }

    private static MockMvc mvcFor(Path database, Path auditFile) {
        InsightsProperties properties =
                new InsightsProperties(database.toString(), auditFile.toString(), 1000, 100);
        InsightsService service =
                new InsightsService(new InsightStore(properties), new AuditReader(properties));
        return MockMvcBuilders.standaloneSetup(new InsightsController(service))
                .setControllerAdvice(new InsightsFailureAdvice())
                .build();
    }

    private JsonNode answer(
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request,
            int expectedStatus)
            throws Exception {
        MvcResult result = mvc.perform(request)
                .andExpect(status().is(expectedStatus))
                .andReturn();
        return JSON.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }
}
