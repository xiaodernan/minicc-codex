package com.minicc.cloud.gateway;

import java.util.Map;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
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
 */
@RestController
@RequestMapping("/api/cached")
public class CachedRouteController {

    private final UpstreamHealthProbe probe;

    public CachedRouteController(UpstreamHealthProbe probe) {
        this.probe = probe;
    }

    @GetMapping("/inspector/status")
    // M8-T826: the key comes from CacheKeys' literals. SpEL needs a compile-time
    // constant, so the literals live there and this annotation is their mirror;
    // ShippedCacheKeysAgreeTest pins that the two never drift apart.
    @Cacheable(value = CacheKeys.CACHE_NAME, key = "'" + CacheKeys.INSPECTOR_STATUS + "'")
    public Mono<ResponseEntity<Map<String, Object>>> inspectorStatus() {
        return probe.probe("minicc-cloud-inspector")
                .map(health -> ResponseEntity.ok(Map.of(
                        "service", "inspector",
                        "cached", true,
                        "upstreamStatus", health.status())));
    }

    @GetMapping("/insights/summary")
    @Cacheable(value = CacheKeys.CACHE_NAME, key = "'" + CacheKeys.INSIGHTS_SUMMARY + "'")
    public Mono<ResponseEntity<Map<String, Object>>> insightsSummary() {
        return probe.probe("minicc-cloud-insights")
                .map(health -> ResponseEntity.ok(Map.of(
                        "service", "insights",
                        "cached", true,
                        "upstreamStatus", health.status())));
    }
}
