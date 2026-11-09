package com.minicc.cloud.tasks;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/**
 * Reads snapshots out of the store and decides what a list may carry.
 *
 * <p>The database row is the truth; the snapshot's {@code status} and
 * {@code preview} are lifted out of it here so the list endpoint never
 * serialises the event log. A payload that is not JSON is a damaged snapshot,
 * not an empty one.
 */
@Service
public class TaskService {

    private static final int PREVIEW_CHARS = 160;

    private final TaskStore store;
    private final TasksProperties properties;
    private final ObjectMapper mapper;

    public TaskService(TaskStore store, TasksProperties properties, ObjectMapper mapper) {
        this.store = store;
        this.properties = properties;
        this.mapper = mapper;
    }

    public TaskPage list(String workspace, int requestedLimit) {
        if (requestedLimit < 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "limit 必须大于 0，收到=" + requestedLimit);
        }
        int limit = Math.min(requestedLimit, properties.maxLimit());
        List<TaskSummary> tasks = store.list(workspace, limit).stream().map(this::summarize).toList();
        return new TaskPage(tasks, requestedLimit > properties.maxLimit(), limit);
    }

    public TaskDetail find(String taskId) {
        TaskRow row = store.find(taskId).orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "这个 id 不存在：" + taskId));
        return new TaskDetail(row.taskId(), row.createdAt(), row.workspacePath(), parse(row));
    }

    private TaskSummary summarize(TaskRow row) {
        JsonNode snapshot = parse(row);
        return new TaskSummary(
                row.taskId(),
                text(snapshot, "status"),
                row.createdAt(),
                row.workspacePath(),
                preview(snapshot));
    }

    private JsonNode parse(TaskRow row) {
        JsonNode snapshot;
        try {
            snapshot = mapper.readTree(row.payload());
        } catch (JsonProcessingException exc) {
            throw new CorruptSnapshotException(row.taskId(), exc.getOriginalMessage());
        }
        if (snapshot == null || !snapshot.isObject()) {
            throw new CorruptSnapshotException(row.taskId(), "顶层不是 JSON 对象");
        }
        return snapshot;
    }

    private static String text(JsonNode snapshot, String field) {
        JsonNode node = snapshot.get(field);
        return node != null && node.isTextual() ? node.asText() : null;
    }

    /** The snapshot's own short form: {@code preview}, else the prompt's head. */
    private static String preview(JsonNode snapshot) {
        for (String field : List.of("preview", "prompt")) {
            JsonNode node = snapshot.get(field);
            if (node != null && node.isTextual() && !node.asText().isBlank()) {
                String value = node.asText();
                return value.length() <= PREVIEW_CHARS ? value : value.substring(0, PREVIEW_CHARS);
            }
        }
        return null;
    }
}
