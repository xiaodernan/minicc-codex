package com.minicc.cloud.gateway;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

/**
 * Production probe over a {@code lb://} route resolved by client-side load balancing,
 * so the gateway answers cache misses without embedding any upstream's host/port.
 * An unreachable upstream is reported as {@code UNKNOWN} rather than thrown, so a
 * cached answer stays honest about what it saw.
 *
 * <p>Each probe is bounded by a timeout (default 2s, {@code MINICC_GATEWAY_PROBE_TIMEOUT_MS}):
 * a hung upstream must never wedge {@code /api/health/all} — an aggregate answer that
 * waits for the slowest backend is a worse answer than one that reports {@code UNKNOWN}.
 */
public class HttpUpstreamHealthProbe implements UpstreamHealthProbe {
    private final WebClient upstreamWebClient;
    private final Duration timeout;

    public HttpUpstreamHealthProbe(WebClient upstreamWebClient) {
        this(upstreamWebClient, Duration.ofSeconds(2));
    }

    public HttpUpstreamHealthProbe(WebClient upstreamWebClient, Duration timeout) {
        this.upstreamWebClient = upstreamWebClient;
        this.timeout = timeout;
    }

    @Override
    public Mono<UpstreamHealth> probe(String service) {
        return upstreamWebClient.get()
                .uri("lb://" + service + "/actuator/health")
                .retrieve()
                .bodyToMono(JsonNode.class)
                .map(node -> new UpstreamHealth(node.path("status").asText("UNKNOWN")))
                .timeout(timeout)
                .onErrorReturn(new UpstreamHealth("UNKNOWN"));
    }
}
