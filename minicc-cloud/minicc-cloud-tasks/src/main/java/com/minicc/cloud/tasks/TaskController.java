package com.minicc.cloud.tasks;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    /** Says whether {@code limit} was above the configured ceiling. */
    static final String TRUNCATED_HEADER = "X-Minicc-Tasks-Truncated";

    /** The ceiling actually applied, so a client can page without guessing. */
    static final String LIMIT_HEADER = "X-Minicc-Tasks-Limit";

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping
    public ResponseEntity<List<TaskSummary>> list(
            @RequestParam(required = false) String workspace,
            @RequestParam(defaultValue = "20") int limit) {
        TaskPage page = service.list(workspace, limit);
        return ResponseEntity.ok()
                .header(TRUNCATED_HEADER, Boolean.toString(page.truncated()))
                .header(LIMIT_HEADER, Integer.toString(page.limit()))
                .body(page.tasks());
    }

    @GetMapping("/{taskId}")
    public TaskDetail find(@PathVariable String taskId) {
        return service.find(taskId);
    }
}
