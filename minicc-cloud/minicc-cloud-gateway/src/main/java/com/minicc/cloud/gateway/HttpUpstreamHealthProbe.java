package com.minicc.cloud.gateway;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

/**
 * Production probe over a {@code lb://} route resolved by client-side load balancing,
 * so the gateway answers cache misses without embedding any upstream's host/port.
 * An unreachable upstream is reported as {@code UNKNOWN} rather than thrown, so a
 * cached answer stays honest about what it saw.
 */
public class HttpUpstreamHealthProbe implements UpstreamHealthProbe {
    private final WebClient upstreamWebClient;

    public HttpUpstreamHealthProbe(WebClient upstreamWebClient) {
        this.upstreamWebClient = upstreamWebClient;
    }

    @Override
    public Mono<UpstreamHealth> probe(String service) {
        return upstreamWebClient.get()
                .uri("lb://" + service + "/actuator/health")
                .retrieve()
                .bodyToMono(JsonNode.class)
                .map(node -> new UpstreamHealth(node.path("status").asText("UNKNOWN")))
                .onErrorReturn(new UpstreamHealth("UNKNOWN"));
    }
}
