package com.minicc.cloud.evidence;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;

/**
 * One captured CI run. The wire format is snake_case (the blueprint's contract):
 * run_id / head_sha / workflow_name / run_status / job_name / step_name / started_at /
 * logs_tail. Verdict is the raw booleans only - {@code conclusion} is the job's own
 * boolean span. There is deliberately no "reason analysis" field: the evidence is the
 * record, the model does not narrate it on this wire.
 */
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@JsonInclude(JsonInclude.Include.NON_NULL)
public record EvidenceEntry(
        long runId,
        String headSha,
        String workflowName,
        String runStatus,
        String conclusion,
        String jobId,
        String jobName,
        String stepName,
        String startedAt,
        List<String> logsTail,
        String capturedAt) {
}
