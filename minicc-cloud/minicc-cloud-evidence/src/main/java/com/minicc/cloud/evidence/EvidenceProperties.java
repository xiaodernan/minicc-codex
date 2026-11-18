package com.minicc.cloud.evidence;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Where the evidence cache lives and how far a backfill may reach.
 *
 * @param store        the JSONL cache this service owns (its only write target)
 * @param apiBase      GitHub REST base; override for GitHub Enterprise
 * @param repoOwner    the repository owner to backfill runs from (never required to be secret)
 * @param repoName     the repository name to backfill runs from
 * @param token        read from the environment only; may be blank, which means
 *                     unauthenticated reads (60 req/h), never echoed anywhere
 * @param maxEntries   hard ceiling on retained lines in the cache
 * @param maxTailLines hard ceiling on log lines kept per captured job
 * @param maxLogBytes  hard ceiling on bytes read from a job log before it is trimmed
 * @param connectMs    connect timeout for the GitHub API
 * @param readMs       read timeout for the GitHub API
 */
@ConfigurationProperties(prefix = "minicc.cloud.evidence")
public record EvidenceProperties(String store, String apiBase, String repoOwner, String repoName,
        String token, Integer maxEntries, Integer maxTailLines, Integer maxLogBytes,
        Long connectMs, Long readMs) {

    public EvidenceProperties {
        if (store == null || store.isBlank()) {
            throw new IllegalStateException("minicc.cloud.evidence.store must name the JSONL cache to own");
        }
        if (apiBase == null || apiBase.isBlank()) {
            throw new IllegalStateException("minicc.cloud.evidence.api-base must name the GitHub REST base");
        }
        if (repoOwner == null || repoOwner.isBlank()) {
            throw new IllegalStateException("minicc.cloud.evidence.repo-owner must name the repository owner");
        }
        if (repoName == null || repoName.isBlank()) {
            throw new IllegalStateException("minicc.cloud.evidence.repo-name must name the repository");
        }
        // Token may be blank: unauthenticated public-repo reads are legal.
        // It may never be misspelled into a log line, a response body, or an exception message.
        if (token == null) {
            token = "";
        }
        if (maxEntries == null || maxEntries < 1) {
            throw new IllegalStateException("minicc.cloud.evidence.max-entries must be a positive integer");
        }
        if (maxTailLines == null || maxTailLines < 1) {
            throw new IllegalStateException("minicc.cloud.evidence.max-tail-lines must be a positive integer");
        }
        if (maxLogBytes == null || maxLogBytes < 1024) {
            throw new IllegalStateException("minicc.cloud.evidence.max-log-bytes must be at least 1024");
        }
        if (connectMs == null || connectMs < 100) {
            throw new IllegalStateException("minicc.cloud.evidence.connect-ms must be at least 100");
        }
        if (readMs == null || readMs < 100) {
            throw new IllegalStateException("minicc.cloud.evidence.read-ms must be at least 100");
        }
    }

    public boolean hasToken() {
        return token != null && !token.isBlank();
    }
}
