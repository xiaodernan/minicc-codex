package com.minicc.cloud.evidence;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * Fetches one foreign run's truth from the GitHub REST API and nothing else.
 *
 * <p>Three rules hold everywhere in here: the token is read from the environment and
 * never appears in an exception message, a log line, or a response body; an HTTP
 * failure becomes {@link EvidenceBackfillException} with the endpoint's status code
 * but none of its content; and a log body is trimmed to the configured byte ceiling
 * before any line is split, so a runaway job cannot stream gigabytes into the heap.
 */
@Component
public class GithubApiClient implements RunFetcher {

    private static final ObjectMapper JSON = new ObjectMapper();

    private final EvidenceProperties properties;
    private final HttpClient http;

    public GithubApiClient(EvidenceProperties properties) {
        this.properties = properties;
        this.http = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NORMAL)
                .connectTimeout(Duration.ofMillis(properties.connectMs()))
                .build();
    }

    @Override
    public EvidenceEntry fetch(long runId) {
        JsonNode run = get(runUrl(runId), "run");
        String workflowName = text(run, "name");
        String headSha = text(run, "head_sha");
        String status = text(run, "status");
        String conclusion = text(run, "conclusion");
        String startedAt = firstNonBlank(text(run, "run_started_at"), text(run, "created_at"));

        JsonNode jobs = get(jobsUrl(runId), "jobs");
        JsonNode job = pickJob(jobs);
        String jobId = job == null ? null : text(job, "id");
        String jobName = job == null ? null : text(job, "name");
        String stepName = job == null ? null : failedStepName(job);
        String jobStartedAt = job == null ? null : firstNonBlank(text(job, "started_at"), startedAt);

        List<String> tail;
        if (job == null) {
            tail = List.of();
        } else if (jobId == null) {
            tail = List.of("job id not captured; logs unavailable");
        } else {
            tail = logTail(jobId);
        }

        return new EvidenceEntry(
                runId,
                headSha,
                workflowName,
                status,
                conclusion,
                jobId,
                jobName,
                stepName,
                jobStartedAt,
                tail,
                Instant.now().toString());
    }

    private String runUrl(long runId) {
        return apiBase() + "/repos/" + properties.repoOwner() + "/" + properties.repoName()
                + "/actions/runs/" + runId;
    }

    private String jobsUrl(long runId) {
        return apiBase() + "/repos/" + properties.repoOwner() + "/" + properties.repoName()
                + "/actions/runs/" + runId + "/jobs?per_page=100";
    }

    private String logsUrl(String jobId) {
        return apiBase() + "/repos/" + properties.repoOwner() + "/" + properties.repoName()
                + "/actions/jobs/" + jobId + "/logs";
    }

    private String apiBase() {
        String base = properties.apiBase();
        return base.endsWith("/") ? base.substring(0, base.length() - 1) : base;
    }

    private JsonNode get(String url, String what) {
        HttpRequest request = baseRequest(url).build();
        try {
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            int code = response.statusCode();
            if (code == 404) {
                throw new EvidenceBackfillException("github " + what + " not found (404) for this run id");
            }
            if (code == 401 || code == 403) {
                // 403 also covers rate limiting; the answer never leaks the token or its absence.
                throw new EvidenceBackfillException("github " + what + " refused (" + code + ") - unauthorized or rate-limited");
            }
            if (code >= 300) {
                throw new EvidenceBackfillException("github " + what + " answered " + code);
            }
            return JSON.readTree(response.body());
        } catch (EvidenceBackfillException exc) {
            throw exc;
        } catch (java.net.http.HttpTimeoutException exc) {
            throw new EvidenceBackfillException("github " + what + " timed out after " + properties.readMs() + " ms", exc);
        } catch (java.io.IOException exc) {
            // Content of this exception is never echoed verbatim; only the class.
            throw new EvidenceBackfillException("github " + what + " unreachable: " + exc.getClass().getSimpleName(), exc);
        } catch (Exception exc) {
            // The catch must never smuggle the token into the message.
            throw new EvidenceBackfillException("github " + what + " failed: " + exc.getClass().getSimpleName(), exc);
        }
    }

    private List<String> logTail(String jobId) {
        if (jobId == null) {
            return List.of();
        }
        HttpRequest request = baseRequest(logsUrl(jobId))
                .setHeader("Accept", "application/vnd.github+json, text/plain")
                .timeout(Duration.ofMillis(properties.readMs()))
                .build();
        try {
            HttpResponse<InputStream> response = http.send(request, HttpResponse.BodyHandlers.ofInputStream());
            int code = response.statusCode();
            if (code == 404) {
                return List.of("logs not found for job " + jobId);
            }
            if (code >= 300) {
                return List.of("logs unavailable (http " + code + ")");
            }
            long cap = properties.maxLogBytes();
            long kept = 0;
            RollingTail tail = new RollingTail(cap);
            try (InputStream in = response.body()) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = in.read(buffer)) != -1) {
                    tail.offer(buffer, read);
                    kept += read;
                    if (kept > cap * 4L) {
                        // The job is streaming gigabytes; the tail is all we keep.
                        break;
                    }
                }
            }
            String text = new String(tail.bytes(), StandardCharsets.UTF_8);
            List<String> lines = new ArrayList<>();
            for (String line : text.split("\\R")) {
                if (!line.isBlank()) {
                    lines.add(line);
                }
            }
            int from = Math.max(0, lines.size() - properties.maxTailLines());
            return List.copyOf(lines.subList(from, lines.size()));
        } catch (EvidenceBackfillException exc) {
            throw exc;
        } catch (Exception exc) {
            // Logs are best-effort; the run record still stands without them.
            return List.of("logs unavailable (" + exc.getClass().getSimpleName() + ")");
        }
    }

    private HttpRequest.Builder baseRequest(String url) {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .GET()
                .timeout(Duration.ofMillis(properties.readMs()))
                .setHeader("Accept", "application/vnd.github+json")
                .setHeader("X-GitHub-Api-Version", "2022-11-28");
        if (properties.hasToken()) {
            // The token is attached only to the outbound header - never logged.
            builder.setHeader("Authorization", "Bearer " + properties.token());
        }
        return builder;
    }

    private static JsonNode pickJob(JsonNode jobs) {
        JsonNode array = jobs.path("jobs");
        if (!array.isArray() || array.isEmpty()) {
            return null;
        }
        JsonNode failed = null;
        for (JsonNode job : array) {
            String conclusion = text(job, "conclusion");
            if ("failure".equals(conclusion) || "cancelled".equals(conclusion) || "timed_out".equals(conclusion)) {
                return job;
            }
            if (failed == null) {
                failed = job;
            }
        }
        return failed;
    }

    private static String failedStepName(JsonNode job) {
        for (JsonNode step : job.path("steps")) {
            String conclusion = text(step, "conclusion");
            if ("failure".equals(conclusion) || "cancelled".equals(conclusion)) {
                return text(step, "name");
            }
        }
        return null;
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null) {
            return null;
        }
        if (value.isTextual() && !value.asText().isBlank()) {
            return value.asText();
        }
        if (value.isNumber()) {
            // GitHub emits ids (run/job/step) as JSON numbers - they are ids, not measures.
            return value.asText();
        }
        return null;
    }

    private static String firstNonBlank(String first, String second) {
        return first != null && !first.isBlank() ? first : second;
    }

    /** Rolling ring of the newest bytes of a log stream. */
    private static final class RollingTail {
        private final long capacity;
        private final ByteArrayOutputStream buffer = new ByteArrayOutputStream(1024);

        RollingTail(long capacity) {
            this.capacity = capacity;
        }

        void offer(byte[] chunk, int length) {
            buffer.write(chunk, 0, length);
            long excess = buffer.size() - capacity;
            if (excess > 0) {
                byte[] bytes = buffer.toByteArray();
                buffer.reset();
                buffer.write(bytes, (int) excess, (int) (bytes.length - excess));
            }
        }

        byte[] bytes() {
            return buffer.toByteArray();
        }
    }
}
