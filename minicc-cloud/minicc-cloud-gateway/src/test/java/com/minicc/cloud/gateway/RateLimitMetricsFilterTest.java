package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * M8-T886 — the 429 counter increments exactly when the gateway refuses a
 * request, and never otherwise. The rejection itself is the rate limiter's;
 * this filter only reports it, so the test drives the smallest possible
 * chain: one fake route, one fake status.
 */
class RateLimitMetricsFilterTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final RateLimitMetricsFilter filter = new RateLimitMetricsFilter(registry);

    @Test
    void theFilterWrapsTheWholeChain() {
        // The outermost position is load-bearing: the Redis rate limiter
        // answers 429 without calling further down the chain, so a filter
        // ordered after it would never see a single rejection — the
        // metrics would ship as a dead counter that only passes its own
        // unit test. Live-verified at /actuator/metrics/gateway.rate_limited.
        assertThat(filter.getOrder()).isEqualTo(Ordered.HIGHEST_PRECEDENCE);
    }

    @Test
    void aRefusedRequestIncrementsTheCounterForItsRoute() {
        ServerWebExchange exchange = exchangeWithRoute("tasks");
        runChain(exchange, HttpStatus.TOO_MANY_REQUESTS);
        assertThat(registry.counter(RateLimitMetricsFilter.COUNTER, "route", "tasks").count())
                .isEqualTo(1.0);
    }

    @Test
    void aForwardedRequestIncrementsNothing() {
        ServerWebExchange exchange = exchangeWithRoute("tasks");
        runChain(exchange, HttpStatus.OK);
        assertThat(registry.find(RateLimitMetricsFilter.COUNTER).counters()).isEmpty();
    }

    @Test
    void aRefusalWithoutRouteContextLandsInTheUnknownBucket() {
        ServerWebExchange exchange = MockServerWebExchange
                .from(MockServerHttpRequest.get("/api/tasks").build());
        runChain(exchange, HttpStatus.TOO_MANY_REQUESTS);
        assertThat(registry.counter(RateLimitMetricsFilter.COUNTER, "route", "unknown").count())
                .isEqualTo(1.0);
    }

    private void runChain(ServerWebExchange exchange, HttpStatus status) {
        GatewayFilterChain chain = new GatewayFilterChain() {
            @Override
            public Mono<Void> filter(ServerWebExchange ex) {
                ex.getResponse().setStatusCode(status);
                return Mono.empty();
            }
        };
        filter.filter(exchange, chain).block();
    }

    private static ServerWebExchange exchangeWithRoute(String id) {
        Route route = Route.async()
                .id(id)
                .uri(URI.create("lb://" + id))
                .order(0)
                .predicate(exchange -> true)
                .build();
        ServerWebExchange exchange = MockServerWebExchange
                .from(MockServerHttpRequest.get("/api/" + id).build());
        exchange.getAttributes().put(ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR, route);
        return exchange;
    }
}
