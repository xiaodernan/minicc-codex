package com.minicc.cloud.insights;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Files;
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
final class InsightsFixture {

    private static final ObjectMapper JSON = new ObjectMapper();

    private InsightsFixture() {
    }

    static Path database(Path directory) {
        Path db = directory.resolve("tasks.sqlite3");
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

    static String snapshot(String taskId, String status) {
        ObjectNode root = JSON.createObjectNode();
        root.put("task_id", taskId);
        root.put("status", status);
        root.put("preview", "fixture preview for " + taskId);
        return root.toString();
    }

    static Path auditLog(Path directory, String... lines) {
        Path audit = directory.resolve("audit.jsonl");
        try {
            Files.writeString(audit, String.join("\n", lines) + (lines.length == 0 ? "" : "\n"));
        } catch (java.io.IOException exc) {
            throw new IllegalStateException("the fixture audit log could not be written", exc);
        }
        return audit;
    }
}
