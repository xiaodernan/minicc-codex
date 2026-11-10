package com.minicc.cloud.tasks;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
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
 * The HTTP shape: a body that is an array, truncation in a header (an array
 * cannot carry a sibling field), and failure statuses that a client cannot
 * mistake for "no tasks".
 */
class TaskControllerTest {

    private static final String EVENT_MARKER = "EVENT-LOG-MUST-NOT-LEAVE-THE-DETAIL";
    private static final ObjectMapper JSON = new ObjectMapper();

    @TempDir Path temp;

    private Path db;
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        db = TasksFixture.database(temp);
        mvc = mvcFor(db, 2);
        TasksFixture.insert(db, "old", 100.0, "ws-a",
                TasksFixture.snapshot("old", "completed", "x".repeat(300), EVENT_MARKER));
        TasksFixture.insert(db, "middle", 200.0, "ws-a",
                TasksFixture.snapshot("middle", "running", "y".repeat(300), EVENT_MARKER));
        TasksFixture.insert(db, "new", 300.0, "ws-b",
                TasksFixture.snapshot("new", "queued", "z".repeat(300), EVENT_MARKER));
    }

    @Test
    void theListIsAnArrayWithTrimmedEntriesNewestFirst() throws Exception {
        MvcResult result = mvc.perform(get("/api/tasks").param("limit", "50"))
                .andExpect(status().isOk())
                .andExpect(header().string(TaskController.TRUNCATED_HEADER, "true"))
                .andExpect(header().string(TaskController.LIMIT_HEADER, "2"))
                .andReturn();
        String raw = result.getResponse().getContentAsString(StandardCharsets.UTF_8);
        JsonNode body = JSON.readTree(raw);

        assertThat(body.isArray()).isTrue();
        assertThat(body).hasSize(2);
        assertThat(body.get(0).get("task_id").asText()).isEqualTo("new");
        assertThat(body.get(1).get("task_id").asText()).isEqualTo("middle");
        assertThat(body.get(0).size()).isEqualTo(5);
        assertThat(body.get(0).has("payload")).isFalse();
        assertThat(body.get(0).get("preview").asText()).hasSize(160);
        assertThat(body.get(0).get("created_at").asDouble()).isEqualTo(300.0);
        assertThat(raw).doesNotContain(EVENT_MARKER);
        assertThat(raw).doesNotContain("\"payload\"");
    }

    @Test
    void aLimitWithinTheCeilingIsNotMarkedTruncated() throws Exception {
        mvc.perform(get("/api/tasks").param("limit", "1"))
                .andExpect(status().isOk())
                .andExpect(header().string(TaskController.TRUNCATED_HEADER, "false"))
                .andExpect(header().string(TaskController.LIMIT_HEADER, "1"));
    }

    @Test
    void theDetailReturnsTheWholeSnapshot() throws Exception {
        JsonNode body = answer(get("/api/tasks/middle"), 200);

        assertThat(body.get("task_id").asText()).isEqualTo("middle");
        assertThat(body.get("workspace_path").asText()).isEqualTo("ws-a");
        assertThat(body.get("payload").get("status").asText()).isEqualTo("running");
        assertThat(body.get("payload").get("events").get(0).asText()).isEqualTo(EVENT_MARKER);
    }

    @Test
    void anUnknownIdIsA404SayingThisIdDoesNotExist() throws Exception {
        JsonNode body = answer(get("/api/tasks/absent"), 404);

        assertThat(body.get("reason").asText()).contains("这个 id 不存在").contains("absent");
        assertThat(body.has("payload")).isFalse();
    }

    @Test
    void aMissingDatabaseIsA503ThatNamesThePathAndNeverAnEmptyArray() throws Exception {
        Path missing = temp.resolve("nowhere").resolve("tasks.sqlite3");
        MockMvc absent = mvcFor(missing, 2);

        MvcResult result = absent.perform(get("/api/tasks"))
                .andExpect(status().isServiceUnavailable())
                .andReturn();
        JsonNode body = JSON.readTree(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8));

        assertThat(body.get("error").asText()).isEqualTo("tasks-db-unavailable");
        assertThat(body.get("reason").asText())
                .contains("任务库不存在")
                .contains(missing.toString());
        assertThat(result.getResponse().getContentAsString(StandardCharsets.UTF_8))
                .doesNotStartWith("[");
    }

    @Test
    void aCorruptSnapshotIsA500ThatSaysTheSnapshotIsBroken() throws Exception {
        TasksFixture.insert(db, "broken", 400.0, "ws-a", "not json at all");

        JsonNode body = answer(get("/api/tasks/broken"), 500);

        assertThat(body.get("error").asText()).isEqualTo("task-snapshot-corrupt");
        assertThat(body.get("reason").asText()).contains("快照损坏").contains("broken");
    }

    private static MockMvc mvcFor(Path database, int maxLimit) {
        TasksProperties properties = new TasksProperties(database.toString(), maxLimit);
        TaskService service =
                new TaskService(new TaskStore(properties), properties, new ObjectMapper());
        return MockMvcBuilders.standaloneSetup(new TaskController(service))
                .setControllerAdvice(new TaskFailureAdvice())
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
