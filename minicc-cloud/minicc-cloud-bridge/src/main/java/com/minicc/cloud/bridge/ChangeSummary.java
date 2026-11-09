package com.minicc.cloud.bridge;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.ArrayList;
import java.util.List;

/**
 * The workspace change summary, with every "unknown" kept distinct from zero.
 *
 * <p>{@code totalFiles} is nullable on purpose. A failed {@code git status} read
 * makes the Python side answer {@code total_files: 0} beside a non-null
 * {@code status_read_error} (M8-T548); a caller that reads only the number sees a
 * clean workspace. {@link #partial()} is the question a service must ask before
 * it is allowed to say "nothing changed".
 *
 * @param files                the shown rows, capped by the Python side
 * @param totalFiles           every changed file, including rows outside the cap
 * @param additions            null when any row could not be counted (M8-T569)
 * @param deletions            null for the same reason
 * @param filesWithoutCounts   how many rows blanked those two totals
 * @param truncated            true when the shown list is shorter than the total
 * @param auditWindowTruncated true when the trail was cut by the byte window
 * @param auditBytesUnread     bytes never read; null when the trail was unreadable
 * @param auditRecordsSplit    records the window began inside of; null likewise
 * @param statusReadError      why the git status read failed, or null
 * @param auditReadError       why the fallback trail read failed, or null
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ChangeSummary(
        List<ChangeRow> files,
        Integer totalFiles,
        Integer additions,
        Integer deletions,
        Integer filesWithoutCounts,
        Boolean truncated,
        Integer shownFiles,
        Boolean auditWindowTruncated,
        Integer auditBytesUnread,
        Integer auditRecordsSplit,
        String statusReadError,
        String auditReadError,
        Integer auditUnreadableLines,
        Integer auditRecordsWithoutPath,
        Integer auditRefusedRecords,
        Integer auditRecordsWithoutAction) {

    /** True when this answer is not the whole truth. */
    public boolean partial() {
        return !partialReasons().isEmpty();
    }

    /**
     * Why the answer cannot be read as complete, in the reader's own words.
     * An unknown count is a reason just as a positive one is: null means the
     * trail could not be read, which is not the claim that nothing was missed.
     */
    public List<String> partialReasons() {
        List<String> reasons = new ArrayList<>();
        if (statusReadError != null) {
            reasons.add("git status could not be read: " + statusReadError);
        }
        if (auditReadError != null) {
            reasons.add("the audit trail could not be read: " + auditReadError);
        }
        if (totalFiles == null) {
            reasons.add("the total number of changed files is unknown");
        }
        if (additions == null || deletions == null) {
            reasons.add("line totals are unknown because "
                    + (filesWithoutCounts == null ? "some" : filesWithoutCounts)
                    + " row(s) could not be counted");
        }
        if (Boolean.TRUE.equals(truncated)) {
            reasons.add("the file list was capped at " + shownFiles + " of " + totalFiles);
        }
        if (Boolean.TRUE.equals(auditWindowTruncated)) {
            reasons.add("the audit trail was cut by the byte window");
        }
        if (auditBytesUnread == null) {
            reasons.add("the number of unread audit bytes is unknown");
        } else if (auditBytesUnread > 0) {
            reasons.add(auditBytesUnread + " bytes of the audit trail were never read");
        }
        if (auditRecordsSplit == null) {
            reasons.add("the number of split audit records is unknown");
        } else if (auditRecordsSplit > 0) {
            reasons.add(auditRecordsSplit + " audit record(s) were cut and not read back whole");
        }
        if (auditUnreadableLines == null) {
            reasons.add("the number of unreadable audit lines is unknown");
        } else if (auditUnreadableLines > 0) {
            reasons.add(auditUnreadableLines + " audit line(s) could not be read");
        }
        return List.copyOf(reasons);
    }
}