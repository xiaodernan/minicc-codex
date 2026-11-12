package com.minicc.cloud.gateway;

import reactor.core.publisher.Mono;

/**
 * Read-side probe of the inspector's {@code /api/changes?workspace=<path>} endpoint,
 * shaped like {@link UpstreamHealthProbe}: an interface so tests swap a fake and
 * production runs over the shared {@code lb://} WebClient.
 */
public interface InspectorChangesProbe {
    /** Fetch the raw JSON body for {@code workspace}; timeouts/errors surface as {@code Mono.error}. */
    Mono<String> fetchChanges(String workspace);
}
