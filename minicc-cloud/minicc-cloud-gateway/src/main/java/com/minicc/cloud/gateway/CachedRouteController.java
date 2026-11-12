package com.minicc.cloud.gateway;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;

/**
 * Cached routes through the gateway.
 *
 * <p>Each downstream call is cached in Redis with a short TTL so that rapid polling
 * from the CLI does not repeatedly hit the inspector or insights services. The cache
 * key includes the service name and path, so different services and different
 * endpoints are cached independently.
 *
 * <p>The payload is real: every miss probes the upstream's own {@code /actuator/health}
 * through client-side load balancing, so a cached row is only as stale as the TTL —
 * a value with a fresh timestamp is a genuine reading, not a simulated one.
 *
 * <p>M8-T861: the cacheable work lives in {@link CachedStatusService} and only ever
 * stores plain {@code Serializable} payloads (a {@code Map} or a raw {@code String}).
 * The previous design cached the {@code Mono<ResponseEntity<…>>} itself, which the JDK
 * serializer cannot write — in a real Redis deployment the cache write would have
 * failed outright. Failures here are propagated to the caller (503), never cached.
 */
@RestController
@RequestMapping("/api/cached")
public class CachedRouteController {

    private final CachedStatusService cached;

    public CachedRouteController(CachedStatusService cached) {
        this.cached = cached;
    }

    @GetMapping("/inspector/status")
    public Mono<ResponseEntity<Map<String, Object>>> inspectorStatus() {
        return cached.inspectorStatus().map(ResponseEntity::ok);
    }

    @GetMapping("/insights/summary")
    public Mono<ResponseEntity<Map<String, Object>>> insightsSummary() {
        return cached.insightsSummary().map(ResponseEntity::ok);
    }

    @GetMapping("/inspector/changes")
    public Mono<ResponseEntity<String>> inspectorChanges(
            @RequestParam(value = "workspace", required = false) String workspace) {
        if (workspace == null || workspace.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "workspace query parameter is required");
        }
        return cached.inspectorChanges(workspace.trim())
                .map(body -> ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(body))
                .onErrorReturn(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"upstreamStatus\":\"UNAVAILABLE\"}"));
    }
}
