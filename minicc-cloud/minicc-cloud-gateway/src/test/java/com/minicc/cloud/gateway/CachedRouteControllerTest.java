package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

/**
 * Cached-route payloads must come from the probe, not from a constant map —
 * a cached route that shows the same literal status forever hides a dead upstream.
 * The service bean is imported explicitly because {@code @WebFluxTest} does not
 * scan {@code @Service} beans; the cache itself is disabled in tests
 * ({@code spring.cache.type=none}), so every request probes per call.
 */
@WebFluxTest(CachedRouteController.class)
@Import(CachedStatusService.class)
class CachedRouteControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @MockBean
    private UpstreamHealthProbe probe;

    @MockBean
    private InspectorChangesProbe changesProbe;

    @Test
    void inspectorStatusReturnsTheUpstreamReading() {
        when(probe.probe("minicc-cloud-inspector")).thenReturn(Mono.just(new UpstreamHealth("UP")));

        webTestClient.get().uri("/api/cached/inspector/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.service").isEqualTo("inspector")
                .jsonPath("$.upstreamStatus").isEqualTo("UP");
    }

    @Test
    void insightsSummaryReturnsTheUpstreamReading() {
        when(probe.probe("minicc-cloud-insights")).thenReturn(Mono.just(new UpstreamHealth("DOWN")));

        webTestClient.get().uri("/api/cached/insights/summary")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.service").isEqualTo("insights")
                .jsonPath("$.upstreamStatus").isEqualTo("DOWN");
    }

    @Test
    void anUnknownServiceYieldsUnknown() {
        when(probe.probe(anyString())).thenReturn(Mono.just(new UpstreamHealth("UNKNOWN")));

        webTestClient.get().uri("/api/cached/inspector/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.upstreamStatus").isEqualTo("UNKNOWN");
    }

    @Test
    void cacheDisabledInTestsMeansEveryCallProbesOnce() {
        // Tests run with spring.cache.type=none (no CacheManager), so @Cacheable is a
        // no-op here: every request must reach the probe exactly its own time.
        when(probe.probe("minicc-cloud-inspector")).thenReturn(Mono.just(new UpstreamHealth("UP")));

        webTestClient.get().uri("/api/cached/inspector/status").exchange().expectStatus().isOk();
        webTestClient.get().uri("/api/cached/inspector/status").exchange().expectStatus().isOk();
        verify(probe, org.mockito.Mockito.times(2)).probe("minicc-cloud-inspector");
    }

    @Test
    void cachedChangesReturnsTheProbeBody() {
        when(changesProbe.fetchChanges("/repo")).thenReturn(Mono.just("{\"files\":2}"));

        webTestClient.get().uri("/api/cached/inspector/changes?workspace=/repo")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.files").isEqualTo(2);
    }

    @Test
    void cachedChangesWithoutWorkspaceIs400() {
        webTestClient.get().uri("/api/cached/inspector/changes")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void cachedChangesPropagatesUpstreamFailureAs503() {
        when(changesProbe.fetchChanges(anyString())).thenReturn(Mono.error(new RuntimeException("boom")));

        webTestClient.get().uri("/api/cached/inspector/changes?workspace=/repo")
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody()
                .jsonPath("$.upstreamStatus").isEqualTo("UNAVAILABLE");
    }

    @Test
    void statusPayloadsArePlainSerializableMaps() {
        // The Redis cache stores whatever the service returns under the hood;
        // a non-serializable payload breaks the real Redis path.
        Map<String, Object> payload = CachedStatusService.statusPayload("inspector", "UP");
        assertThat(payload).containsEntry("service", "inspector").containsEntry("upstreamStatus", "UP");
        assertThat(payload).isInstanceOf(java.io.Serializable.class);
        payload.values().forEach(v -> assertThat(v).isInstanceOf(java.io.Serializable.class));
    }
}
