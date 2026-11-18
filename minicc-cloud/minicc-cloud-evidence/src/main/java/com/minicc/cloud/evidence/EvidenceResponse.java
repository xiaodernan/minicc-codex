package com.minicc.cloud.evidence;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * The only JSON this service ever emits. Always the same envelope, whether the
 * payload says "facts" or admits there are none.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record EvidenceResponse(
        boolean present,
        String generatedAt,
        long count,
        long skippedLines,
        String reason,
        EvidenceEntry latest,
        List<EvidenceEntry> entries) {
}
