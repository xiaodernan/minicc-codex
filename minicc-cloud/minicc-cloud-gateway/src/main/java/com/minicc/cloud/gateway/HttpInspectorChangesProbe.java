package com.minicc.cloud.gateway;

import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

/**
 * Production probe over a {@code lb://}-routed {@link WebClient}; the inspector's own
 * scan budget is 30s, so 35s bounds the wait without discarding results the inspector
 * was still able to produce. Errors are propagated (the caller decides the error body)
 * instead of silently becoming empty content.
 */
public class HttpInspectorChangesProbe implements InspectorChangesProbe {
    private final WebClient upstreamWebClient;
    private final Duration timeout;

    public HttpInspectorChangesProbe(WebClient upstreamWebClient, Duration timeout) {
        this.upstreamWebClient = upstreamWebClient;
        this.timeout = timeout;
    }

    @Override
    public Mono<String> fetchChanges(String workspace) {
        return upstreamWebClient.get()
                .uri(uriBuilder -> uriBuilder
                        .scheme("lb")
                        .host("minicc-cloud-inspector")
                        .path("/api/changes")
                        .queryParam("workspace", workspace)
                        .build())
                .retrieve()
                .bodyToMono(String.class)
                .timeout(timeout);
    }
}
