package com.minicc.cloud.tasks;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.web.server.ResponseStatusException;

/**
 * The read path's promises are made here: newest first, bounded, trimmed in
 * the list, complete in the detail, and never a fabricated empty answer.
 */
class TaskQueryServiceTest {

    private static final String EVENT_MARKER = "EVENT-LOG-ONLY-IN-THE-DETAIL";

    @TempDir Path temp;

    private Path db;
    private TasksProperties properties;
    private TaskService service;

    @BeforeEach
    void setUp() {
        db = TasksFixture.database(temp);
        properties = new TasksProperties(db.toString(), 100);
        service = new TaskService(new TaskStore(properties), properties, new ObjectMapper());
    }

    @Test
    void theListIsNewestFirstAndLimitOneKeepsOnlyTheHead() {
        TasksFixture.insert(db, "older", 100.0, "ws-a", TasksFixture.snapshot("older", "completed", "old", EVENT_MARKER));
        TasksFixture.insert(db, "newer", 200.0, "ws-a", TasksFixture.snapshot("newer", "running", "new", EVENT_MARKER));

        assertThat(service.list(null, 20).tasks())
                .extracting(TaskSummary::taskId)
                .containsExactly("newer", "older");
        assertThat(service.list(null, 1).tasks())
                .extracting(TaskSummary::taskId)
                .containsExactly("newer");
    }

    @Test
    void aWorkspaceFilterKeepsOnlyThatWorkspace() {
        TasksFixture.insert(db, "a", 1.0, "ws-a", TasksFixture.snapshot("a", "completed", "a", EVENT_MARKER));
        TasksFixture.insert(db, "b", 2.0, "ws-b", TasksFixture.snapshot("b", "completed", "b", EVENT_MARKER));

        assertThat(service.list("ws-b", 20).tasks())
                .extracting(TaskSummary::taskId)
                .containsExactly("b");
    }

    @Test
    void aLimitAboveTheCeilingIsClampedAndSaysItWasTruncated() {
        TasksFixture.insert(db, "a", 1.0, "ws-a", TasksFixture.snapshot("a", "completed", "a", EVENT_MARKER));
        TasksFixture.insert(db, "b", 2.0, "ws-b", TasksFixture.snapshot("b", "completed", "b", EVENT_MARKER));
        TasksProperties ceilingOfOne = new TasksProperties(db.toString(), 1);
        TaskService bounded = new TaskService(new TaskStore(ceilingOfOne), ceilingOfOne, new ObjectMapper());

        TaskPage page = bounded.list(null, 50);

        assertThat(page.truncated()).isTrue();
        assertThat(page.limit()).isEqualTo(1);
        assertThat(page.tasks()).hasSize(1);
        assertThat(bounded.list(null, 1).truncated()).isFalse();
    }

    @Test
    void theListEntryCarriesThePreviewAndNotThePayload() {
        String prompt = "起".repeat(300);
        TasksFixture.insert(db, "a", 1.0, "ws-a", TasksFixture.snapshot("a", "completed", prompt, EVENT_MARKER));

        TaskSummary summary = service.list(null, 20).tasks().get(0);

        assertThat(summary.status()).isEqualTo("completed");
        assertThat(summary.preview()).hasSize(160);
        assertThat(summary.preview()).isEqualTo(prompt.substring(0, 160));
    }

    @Test
    void theDetailCarriesTheWholeSnapshot() {
        TasksFixture.insert(db, "a", 1.0, "ws-a", TasksFixture.snapshot("a", "completed", "do it", EVENT_MARKER));

        TaskDetail detail = service.find("a");

        assertThat(detail.taskId()).isEqualTo("a");
        assertThat(detail.workspacePath()).isEqualTo("ws-a");
        assertThat(detail.payload().get("status").asText()).isEqualTo("completed");
        assertThat(detail.payload().get("events").get(0).asText()).isEqualTo(EVENT_MARKER);
    }

    @Test
    void anUnknownIdIsANotFoundThatNamesTheId() {
        assertThatThrownBy(() -> service.find("absent"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("这个 id 不存在")
                .hasMessageContaining("absent");
    }

    @Test
    void aMissingDatabaseIsReportedWithItsPath() {
        Path missing = temp.resolve("no-such-directory").resolve("tasks.db");
        TasksProperties absent = new TasksProperties(missing.toString(), 100);
        TaskService reader = new TaskService(new TaskStore(absent), absent, new ObjectMapper());

        assertThatThrownBy(() -> reader.list(null, 20))
                .isInstanceOf(TaskStoreUnavailableException.class)
                .hasMessageContaining("任务库不存在")
                .hasMessageContaining(missing.toString());
    }

    @Test
    void aCorruptSnapshotSaysSoInsteadOfBecomingAnEmptyTask() {
        TasksFixture.insert(db, "broken", 1.0, "ws-a", "{\"task_id\": \"broken\",");

        assertThatThrownBy(() -> service.find("broken"))
                .isInstanceOf(CorruptSnapshotException.class)
                .hasMessageContaining("快照损坏")
                .hasMessageContaining("broken");
        assertThatThrownBy(() -> service.list(null, 20))
                .isInstanceOf(CorruptSnapshotException.class)
                .hasMessageContaining("快照损坏");
    }
}
