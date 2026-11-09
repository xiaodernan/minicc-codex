package com.minicc.cloud.inspector;

import com.minicc.cloud.bridge.ChangeRow;
import java.util.ArrayList;
import java.util.List;

/** One file's diff, labelled with the reasons it may not be the whole story. */
public record DiffReport(boolean partial, List<String> reasons, ChangeRow row) {

    public static DiffReport of(ChangeRow row) {
        List<String> reasons = new ArrayList<>();
        if (row.statusReadError() != null) {
            reasons.add("git status could not be read: " + row.statusReadError());
        }
        if (row.auditReadError() != null) {
            reasons.add("the audit trail could not be read: " + row.auditReadError());
        }
        if (row.uncounted()) {
            reasons.add("this row's line counts are unknown, not zero");
        }
        if (Boolean.TRUE.equals(row.auditWindowTruncated())) {
            reasons.add("the audit trail was cut by the byte window");
        }
        if ("not-in-window".equals(row.deletionPreimage())) {
            reasons.add("the copy this deletion may have had fell outside the window that was read");
        }
        return new DiffReport(!reasons.isEmpty(), List.copyOf(reasons), row);
    }
}