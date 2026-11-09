package com.minicc.cloud.tasks;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * A throwaway SQLite store with the exact schema {@code minicc/task_store.py}
 * creates. Tests never point at the repository's real {@code .minicc/} state.
 */
final class TasksFixture {

    private static final ObjectMapper JSON = new ObjectMapper();

    private TasksFixture() {
    }

    static Path database(Path directory) {
        Path db = directory.resolve("tasks.db");
        try (Connection connection = DriverManager.getConnection("jdbc:sqlite:" + db);
                Statement statement = connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        created_at REAL NOT NULL,
                        workspace_path TEXT NOT NULL DEFAULT '',
                        payload TEXT NOT NULL
                    )
                    """);
        } catch (SQLException exc) {
            throw new IllegalStateException("the fixture database could not be created", exc);
        }
        return db;
    }

    static void insert(Path db, String taskId, double createdAt, String workspacePath, String payload) {
        String sql = "INSERT INTO tasks(task_id, created_at, workspace_path, payload) VALUES (?, ?, ?, ?)";
        try (Connection connection = DriverManager.getConnection("jdbc:sqlite:" + db);
                PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, taskId);
            statement.setDouble(2, createdAt);
            statement.setString(3, workspacePath);
            statement.setString(4, payload);
            statement.executeUpdate();
        } catch (SQLException exc) {
            throw new IllegalStateException("the fixture row could not be inserted", exc);
        }
    }

    /** A snapshot shaped like the engine's: prompt, preview, and a bulk event log. */
    static String snapshot(String taskId, String status, String prompt, String eventMarker) {
        ObjectNode root = JSON.createObjectNode();
        root.put("task_id", taskId);
        root.put("status", status);
        root.put("prompt", prompt);
        // Deliberately as long as the prompt: the service, not the fixture,
        // owns the 160-character cap the list endpoint promises.
        root.put("preview", prompt);
        root.putArray("events").add(eventMarker);
        return root.toString();
    }
}
