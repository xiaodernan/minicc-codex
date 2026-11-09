package com.minicc.cloud.bridge;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * One changed file, as the Python inspector answered it.
 *
 * <p>{@code additions} and {@code deletions} are {@link Integer}, not {@code int}.
 * The Python side sends {@code null} when it could not attribute a count to the
 * row (M8-T565/T569); unboxing that to 0 would turn "I could not count this file"
 * into "this file changed nothing", which is the defect the whole bridge exists
 * to keep out of the Java half.
 *
 * @param additions          lines added, or null when the row could not be counted
 * @param deletions          lines removed, or null for the same reason
 * @param deletionPreimage   what can be said about the content a deletion removed;
 *                           {@code not-in-window} means the trail was cut, not
 *                           that no copy was ever recorded
 * @param auditBytesUnread   bytes of the trail never read; null when the trail
 *                           itself could not be read, which is not zero
 * @param auditRecordsSplit  records the window began inside of; null likewise
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ChangeRow(
        String path,
        String status,
        String patch,
        Integer additions,
        Integer deletions,
        String source,
        String nameResolution,
        String deletionPreimage,
        String statusReadError,
        String auditReadError,
        Integer auditUnreadableLines,
        Boolean auditWindowTruncated,
        Integer auditBytesUnread,
        Integer auditRecordsSplit) {

    /** True when this row's own numbers cannot be trusted as a complete count. */
    public boolean uncounted() {
        return additions == null || deletions == null;
    }

    /** True when the row carries a read failure rather than a clean answer. */
    public boolean readFailed() {
        return statusReadError != null || auditReadError != null;
    }
}