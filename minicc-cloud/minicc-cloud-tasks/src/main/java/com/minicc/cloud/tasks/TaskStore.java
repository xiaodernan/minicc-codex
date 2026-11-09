package com.minicc.cloud.tasks;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * The only thing that touches the Python engine's SQLite file, and it only
 * ever reads.
 *
 * <p>Read-only is enforced twice: the JDBC URL carries SQLite's own
 * {@code mode=ro}, and every connection runs {@code PRAGMA query_only=ON}
 * before a statement is prepared. A missing file is reported, never treated as
 * an empty store.
 */
@Component
public class TaskStore {

    private final Path dbPath;

    public TaskStore(TasksProperties properties) {
        this.dbPath = Path.of(properties.db()).toAbsolutePath().normalize();
    }

    public Path path() {
        return dbPath;
    }

    public List<TaskRow> list(String workspace, int limit) {
        boolean allWorkspaces = workspace == null || workspace.isBlank();
        String sql = "SELECT task_id, created_at, workspace_path, payload FROM tasks"
                + (allWorkspaces ? "" : " WHERE workspace_path = ?")
                + " ORDER BY created_at DESC LIMIT ?";
        try (Connection connection = open();
                PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (!allWorkspaces) {
                statement.setString(index++, workspace);
            }
            statement.setInt(index, limit);
            try (ResultSet rows = statement.executeQuery()) {
                List<TaskRow> tasks = new ArrayList<>();
                while (rows.next()) {
                    tasks.add(row(rows));
                }
                return List.copyOf(tasks);
            }
        } catch (SQLException exc) {
            throw new TaskStoreUnavailableException("任务库读取失败，路径=" + dbPath, exc);
        }
    }

    public Optional<TaskRow> find(String taskId) {
        String sql = "SELECT task_id, created_at, workspace_path, payload FROM tasks WHERE task_id = ?";
        try (Connection connection = open();
                PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, taskId);
            try (ResultSet rows = statement.executeQuery()) {
                return rows.next() ? Optional.of(row(rows)) : Optional.empty();
            }
        } catch (SQLException exc) {
            throw new TaskStoreUnavailableException("任务库读取失败，路径=" + dbPath, exc);
        }
    }

    private static TaskRow row(ResultSet rows) throws SQLException {
        return new TaskRow(
                rows.getString("task_id"),
                rows.getDouble("created_at"),
                rows.getString("workspace_path"),
                rows.getString("payload"));
    }

    private Connection open() {
        if (!Files.isRegularFile(dbPath)) {
            throw new TaskStoreUnavailableException("任务库不存在，路径=" + dbPath);
        }
        String url = "jdbc:sqlite:file:" + dbPath.toString().replace('\\', '/') + "?mode=ro";
        Connection connection = null;
        try {
            connection = DriverManager.getConnection(url);
            try (Statement statement = connection.createStatement()) {
                statement.execute("PRAGMA query_only=ON");
            }
            return connection;
        } catch (SQLException exc) {
            if (connection != null) {
                try {
                    connection.close();
                } catch (SQLException ignored) {
                    // The original failure is the one worth reporting.
                }
            }
            throw new TaskStoreUnavailableException(
                    "任务库无法打开，路径=" + dbPath + "：" + exc.getMessage(), exc);
        }
    }
}
