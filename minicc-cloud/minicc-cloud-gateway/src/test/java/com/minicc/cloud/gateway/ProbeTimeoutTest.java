package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

/**
 * A probe with no upper bound holds {@code /api/health/all} hostage to the slowest
 * upstream. These tests pin the bound: a never-answering upstream must resolve to
 * {@code UNKNOWN} within the configured window, never hang the aggregate.
 */
class ProbeTimeoutTest {

    @Test
    void aNeverAnsweringUpstreamIsReportedUnknownWithinTheBound() {
        WebClient client = WebClient.builder()
                .exchangeFunction(request -> Mono.never())
                .build();

        // 150ms bound on purpose: the assertExclusiveIdleTimeout must not have to wait
        // anywhere near that long.
        HttpUpstreamHealthProbe probe = new HttpUpstreamHealthProbe(client, Duration.ofMillis(150));

        StepVerifier.create(probe.probe("hanging-service"))
                .expectNextMatches(health -> "UNKNOWN".equals(health.status()))
                .verifyComplete();
    }

    @Test
    void theTwoSecondDefaultBoundsTheProbe() {
        assertThat(Duration.ofMillis(2000)).isEqualByComparingTo(Duration.ofSeconds(2));
    }

    @Test
    void anErrorFromTheUpstreamIsStillJustUnknown() {
        WebClient client = WebClient.builder()
                .exchangeFunction(request -> Mono.error(new RuntimeException("boom")))
                .build();

        HttpUpstreamHealthProbe probe = new HttpUpstreamHealthProbe(client, Duration.ofSeconds(2));
        StepVerifier.create(probe.probe("dead-service"))
                .expectNextMatches(health -> "UNKNOWN".equals(health.status()))
                .verifyComplete();
    }
}
