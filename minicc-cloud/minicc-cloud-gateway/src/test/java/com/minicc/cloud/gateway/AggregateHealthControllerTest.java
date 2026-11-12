package com.minicc.cloud.gateway;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

/**
 * Aggregate health must report exactly what the probe returned for every known
 * service. A green claim derived from "some probe said UP somewhere" hides a dead
 * service; this pins it to the real count.
 */
@WebFluxTest(AggregateHealthController.class)
class AggregateHealthControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @MockBean
    private UpstreamHealthProbe probe;

    @Test
    void itReportsUpWhenEveryServiceAnswersUp() {
        when(probe.probe(anyString())).thenReturn(Mono.just(new UpstreamHealth("UP")));

        webTestClient.get().uri("/api/health/all")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.services.length()").isEqualTo(3)
                .jsonPath("$.upCount").isEqualTo(3)
                .jsonPath("$.totalServices").isEqualTo(3)
                .jsonPath("$.services[0].upstreamStatus").isEqualTo("UP");
    }

    @Test
    void itCountsOnlyTheUpServicesCorrectly() {
        when(probe.probe("minicc-cloud-inspector")).thenReturn(Mono.just(new UpstreamHealth("UP")));
        when(probe.probe("minicc-cloud-tasks")).thenReturn(Mono.just(new UpstreamHealth("DOWN")));
        when(probe.probe("minicc-cloud-insights")).thenReturn(Mono.just(new UpstreamHealth("UNKNOWN")));

        webTestClient.get().uri("/api/health/all")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.upCount").isEqualTo(1)
                .jsonPath("$.totalServices").isEqualTo(3);
    }

    @Test
    void itAnswersEvenWhenEveryServiceIsDown() {
        when(probe.probe(anyString())).thenReturn(Mono.just(new UpstreamHealth("DOWN")));

        webTestClient.get().uri("/api/health/all")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.upCount").isEqualTo(0)
                .jsonPath("$.totalServices").isEqualTo(3)
                .jsonPath("$.services[0].upstreamStatus").isEqualTo("DOWN");
    }
}
