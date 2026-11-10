package com.minicc.cloud.insights;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Component;

/**
 * Counts audit lines with a hard cap - an audit that got out of hand must
 * not turn one summary call into a full-file read of something enormous.
 *
 * <p>A missing audit log is the normal first-hour state, not an error: the
 * answer says {@code present: false}. A present but unreadable one is a
 * failure (the caller cannot distinguish "clean" from "blind").
 */
@Component
public class AuditReader {

    private final Path auditPath;
    private final int maxAuditLines;

    public AuditReader(InsightsProperties properties) {
        this.auditPath = Path.of(properties.audit()).toAbsolutePath().normalize();
        this.maxAuditLines = properties.maxAuditLines();
    }

    public AuditSummary read() {
        if (!Files.isRegularFile(auditPath)) {
            return new AuditSummary(false, 0, false, maxAuditLines);
        }
        long lines = 0;
        boolean truncated = false;
        try (BufferedReader reader = Files.newBufferedReader(auditPath, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                lines++;
                if (lines > maxAuditLines) {
                    truncated = true;
                    lines = maxAuditLines;
                    break;
                }
            }
        } catch (IOException | SecurityException exc) {
            throw new InsightStoreUnavailableException(
                    "审计日志打不开：路径=" + auditPath + "，" + exc.getMessage(), exc);
        }
        return new AuditSummary(true, lines, truncated, maxAuditLines);
    }

    public record AuditSummary(boolean present, long lines, boolean truncated, int cappedAt) {
    }
}
