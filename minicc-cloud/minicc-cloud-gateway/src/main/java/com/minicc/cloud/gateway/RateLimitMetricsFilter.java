package com.minicc.cloud.gateway;

import io.micrometer.core.instrument.MeterRegistry;
import java.util.Objects;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * M8-T886 — count the rate limiter's rejections where operators can see them.
 *
 * <p>The Redis token bucket (M8-T882, {@code application-ratelimit.yml}) turns
 * excess traffic into {@code 429}s, but nothing aggregates those: a dashboard
 * or a log scrape sees isolated events, never "how many requests did the
 * gateway refuse in the last 10 minutes, per route". This filter observes the
 * response after the chain and increments a Micrometer counter tagged by
 * route id. It changes no decision — least-precedence, after everything —
 * and costs one status-code read per request.</p>
 *
 * <p>M8-T886 first shipped this at {@code LOWEST_PRECEDENCE} and the counter
 * never moved: the Redis rate limiter answers 429 <em>without calling the
 * rest of the chain</em>, so a filter ordered after it is skipped exactly
 * when there is something to count. Wrapping the whole chain at the
 * outermost position sees the final response regardless of where the 429
 * was minted. Least-precedence is what made it invisible; outermost is
 * what makes it a signal.</p>
 *
 * <p>Actuator exposure is already configured ({@code metrics}); the counter
 * answers at {@code /actuator/metrics/gateway.rate_limited}.</p>
 */
@Component
public class RateLimitMetricsFilter implements GlobalFilter, Ordered {

    static final String COUNTER = "gateway.rate_limited";

    private final MeterRegistry registry;

    public RateLimitMetricsFilter(MeterRegistry registry) {
        this.registry = Objects.requireNonNull(registry, "registry");
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        return chain.filter(exchange).then(Mono.fromRunnable(() -> {
            ServerHttpResponse response = exchange.getResponse();
            if (response.getStatusCode() == HttpStatus.TOO_MANY_REQUESTS) {
                String routeId = routeIdOf(exchange);
                registry.counter(COUNTER, "route", routeId).increment();
            }
        }));
    }

    private static String routeIdOf(ServerWebExchange exchange) {
        Object attr = exchange.getAttribute(ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
        if (attr instanceof Route route && route.getId() != null && !route.getId().isBlank()) {
            return route.getId();
        }
        return "unknown";
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
