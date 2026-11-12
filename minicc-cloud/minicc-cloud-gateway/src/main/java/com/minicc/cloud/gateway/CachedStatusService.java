package com.minicc.cloud.gateway;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

/**
 * M8-T861: the @Cacheable home for the cached routes. The controller builds
 * {@code ResponseEntity}s per request; the cache only ever stores plain
 * {@link java.io.Serializable} payloads (a {@code Map} of Strings/Booleans or a
 * raw {@code String} body), so a real Redis round trip works — the old design
 * cached {@code Mono<ResponseEntity<Map>>}, whose value the JDK serializer
 * cannot write ({@code ResponseEntity} is not {@code Serializable}).
 *
 * <p>Errors propagate out of the cached methods, so a failed upstream probe is
 * never cached as a fake "healthy" answer.
 */
@Service
public class CachedStatusService {

    private final UpstreamHealthProbe probe;
    private final InspectorChangesProbe changesProbe;

    public CachedStatusService(UpstreamHealthProbe probe, InspectorChangesProbe changesProbe) {
        this.probe = probe;
        this.changesProbe = changesProbe;
    }

    public static Map<String, Object> statusPayload(String service, String upstreamStatus) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("service", service);
        payload.put("upstreamStatus", upstreamStatus);
        return payload;
    }

    @Cacheable(value = CacheKeys.CACHE_NAME, key = "'" + CacheKeys.INSPECTOR_STATUS + "'")
    public Mono<Map<String, Object>> inspectorStatus() {
        return probe.probe("minicc-cloud-inspector")
                .map(health -> statusPayload("inspector", health.status()));
    }

    @Cacheable(value = CacheKeys.CACHE_NAME, key = "'" + CacheKeys.INSIGHTS_SUMMARY + "'")
    public Mono<Map<String, Object>> insightsSummary() {
        return probe.probe("minicc-cloud-insights")
                .map(health -> statusPayload("insights", health.status()));
    }

    @Cacheable(value = CacheKeys.CACHE_NAME, key = "'" + CacheKeys.INSPECTOR_CHANGES + ":' + #workspace")
    public Mono<String> inspectorChanges(String workspace) {
        return changesProbe.fetchChanges(workspace);
    }
}
