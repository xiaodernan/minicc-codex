package com.minicc.cloud.inspector;

import com.minicc.cloud.bridge.ChangeSummary;
import java.util.List;

/**
 * A summary plus the explicit statement of whether it can be read as complete.
 * The reasons travel in the body so a client that only renders {@code summary}
 * still cannot mistake a failed read for a clean workspace without ignoring a
 * field that is right beside it.
 */
public record ChangeReport(boolean partial, List<String> reasons, ChangeSummary summary) {

    public static ChangeReport of(ChangeSummary summary) {
        return new ChangeReport(summary.partial(), summary.partialReasons(), summary);
    }
}