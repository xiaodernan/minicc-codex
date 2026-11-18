package com.minicc.cloud.evidence;

/**
 * The seam between the evidence service and GitHub. Implemented by
 * {@link GithubApiClient} in production and by in-memory fakes in tests, so no
 * test ever touches the network or a token.
 */
public interface RunFetcher {

    /** Fetch one run's metadata plus its newest failing (or first) job's trimmed log tail. */
    EvidenceEntry fetch(long runId);
}
