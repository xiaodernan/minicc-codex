package com.minicc.cloud.gateway;

import java.util.Map;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import reactor.core.publisher.Mono;

/**
 * Cached routes through the gateway.
 *
 * <p>Each downstream call is cached in Redis with a short TTL so that rapid
 * polling from the CLI does not repeatedly hit the inspector or insights
 * services.  The cache key includes the service name and path, so different
 * services and different endpoints are cached independently.
 */
@RestController
@RequestMapping("/api/cached")
public class CachedRouteController {

    private final RestClient restClient;

    public CachedRouteController() {
        this.restClient = RestClient.create();
    }

    @GetMapping("/inspector/status")
    // M8-T826: the key comes from CacheKeys' literals. SpEL needs a compile-time
    // constant, so the literals live there and this annotation is their mirror;
    // ShippedCacheKeysAgreeTest pins that the two never drift apart.
    @Cacheable(value = CacheKeys.CACHE_NAME, key = "'" + CacheKeys.INSPECTOR_STATUS + "'")
    public Mono<ResponseEntity<Map<String, Object>>> inspectorStatus() {
        return Mono.just(ResponseEntity.ok(Map.of(
                "service", "inspector",
                "cached", true,
                "message", "inspector status retrieved from cacheable route")));
    }

    @GetMapping("/insights/summary")
    @Cacheable(value = CacheKeys.CACHE_NAME, key = "'" + CacheKeys.INSIGHTS_SUMMARY + "'")
    public Mono<ResponseEntity<Map<String, Object>>> insightsSummary() {
        return Mono.just(ResponseEntity.ok(Map.of(
                "service", "insights",
                "cached", true,
                "message", "insights summary retrieved from cacheable route")));
    }
}
