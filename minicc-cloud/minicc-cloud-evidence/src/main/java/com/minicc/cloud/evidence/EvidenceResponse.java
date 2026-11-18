package com.minicc.cloud.evidence;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;

/**
 * The only JSON this service ever emits. Always the same envelope, whether the
 * payload says "facts" or admits there are none. snake_case throughout, in
 * step with the entries it carries.
 */
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
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
