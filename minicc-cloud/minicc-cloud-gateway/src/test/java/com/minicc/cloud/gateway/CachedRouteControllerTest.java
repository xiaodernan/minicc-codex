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
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

/**
 * Cached-route payloads must come from the probe, not from a constant map —
 * a cached route that shows the same literal status forever hides a dead upstream.
 */
@WebFluxTest(CachedRouteController.class)
class CachedRouteControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @MockBean
    private UpstreamHealthProbe probe;

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
}
