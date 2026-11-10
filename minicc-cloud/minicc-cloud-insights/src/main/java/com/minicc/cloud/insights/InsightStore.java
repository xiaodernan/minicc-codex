package com.minicc.cloud.insights;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.stereotype.Component;

/**
 * The only thing in this service that touches the task database.
 *
 * <p>Two guard rails, same as {@code minicc-cloud-tasks}: every connection is
 * opened {@code mode=ro} and runs {@code PRAGMA query_only=ON}, and the total
 * is a {@code COUNT(*)} so it stays exact even past the per-status scan cap.
 * A missing database is reported, never treated as an empty one.
 */
@Component
public class InsightStore {

    private final Path dbPath;
    private final int maxScanRows;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public InsightStore(InsightsProperties properties) {
        this.dbPath = Path.of(properties.db()).toAbsolutePath().normalize();
        this.maxScanRows = properties.maxScanRows();
    }

    public Path path() {
        return dbPath;
    }

    /** Totals are exact; per-status counts stop at the scan cap. */
    public Summary summary(String workspace) {
        boolean allWorkspaces = workspace == null || workspace.isBlank();
        try (Connection connection = open()) {
            long total = count(connection, allWorkspaces, workspace);
            Double minCreated = extrema(connection, allWorkspaces, workspace, "MIN(created_at)");
            Double maxCreated = extrema(connection, allWorkspaces, workspace, "MAX(created_at)");
            StatusScan scan = scanStatuses(connection, allWorkspaces, workspace);
            return new Summary(total, scan.byStatus(), scan.truncated(), minCreated, maxCreated);
        } catch (InsightStoreUnavailableException exc) {
            throw exc;
        } catch (SQLException exc) {
            throw new InsightStoreUnavailableException("洞察库读取失败：路径=" + dbPath + "，" + exc.getMessage(), exc);
        }
    }

    private long count(Connection connection, boolean allWorkspaces, String workspace) throws SQLException {
        String sql = "SELECT COUNT(*) FROM tasks" + (allWorkspaces ? "" : " WHERE workspace_path = ?");
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            if (!allWorkspaces) {
                statement.setString(1, workspace);
            }
            try (ResultSet rows = statement.executeQuery()) {
                rows.next();
                return rows.getLong(1);
            }
        }
    }

    private Double extrema(Connection connection, boolean allWorkspaces, String workspace, String fn)
            throws SQLException {
        String sql = "SELECT " + fn + " FROM tasks" + (allWorkspaces ? "" : " WHERE workspace_path = ?");
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            if (!allWorkspaces) {
                statement.setString(1, workspace);
            }
            try (ResultSet rows = statement.executeQuery()) {
                rows.next();
                double value = rows.getDouble(1);
                return rows.wasNull() ? null : value;
            }
        }
    }

    private record StatusScan(Map<String, Long> byStatus, boolean truncated) {
    }

    private StatusScan scanStatuses(Connection connection, boolean allWorkspaces, String workspace)
            throws SQLException {
        String sql = "SELECT task_id, payload FROM tasks" + (allWorkspaces ? "" : " WHERE workspace_path = ?")
                + " ORDER BY created_at ASC LIMIT ?";
        Map<String, Long> counts = new TreeMap<>();
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (!allWorkspaces) {
                statement.setString(index++, workspace);
            }
            statement.setInt(index, maxScanRows + 1);
            try (ResultSet rows = statement.executeQuery()) {
                long seen = 0;
                boolean truncated = false;
                while (rows.next()) {
                    seen++;
                    if (seen > maxScanRows) {
                        truncated = true;
                        break;
                    }
                    String status = statusOf(rows.getString("task_id"), rows.getString("payload"));
                    counts.merge(status, 1L, Long::sum);
                }
                return new StatusScan(Map.copyOf(new LinkedHashMap<>(counts)), truncated);
            }
        }
    }

    private String statusOf(String taskId, String payload) {
        JsonNode snapshot;
        try {
            snapshot = MAPPER.readTree(payload);
        } catch (JsonProcessingException exc) {
            throw new CorruptSnapshotException(taskId, exc.getOriginalMessage());
        }
        if (snapshot == null || !snapshot.isObject()) {
            throw new CorruptSnapshotException(taskId, "快照不是 JSON 对象");
        }
        JsonNode status = snapshot.get("status");
        return status != null && status.isTextual() && !status.asText().isBlank()
                ? status.asText()
                : "unknown";
    }

    private Connection open() {
        if (!Files.isRegularFile(dbPath)) {
            throw new InsightStoreUnavailableException("洞察库不存在：路径=" + dbPath);
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
            throw new InsightStoreUnavailableException(
                    "洞察库打不开：路径=" + dbPath + "，" + exc.getMessage(), exc);
        }
    }

    /** The untrusted snapshot error path needs a task id; scan does not keep one. */
    public record Summary(long total, Map<String, Long> byStatus, boolean truncated,
            Double minCreatedAt, Double maxCreatedAt) {
    }
}
