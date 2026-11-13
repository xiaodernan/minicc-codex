package com.minicc.cloud.gateway;

import java.net.InetSocketAddress;
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * Per-client rate-limit key: the caller's IP.
 *
 * <p>Metering by IP is the coarsest fair key a front door accepts — it keeps
 * one runaway client from consuming the whole LLM budget without tracking
 * anything user-specific. Localhost smokes and health checks all map to one
 * bucket, which is deliberate: they refill at the same steady rate.</p>
 *
 * <p>A missing RemoteAddress (can't happen over a real socket, but unit
 * harnesses can build exchanges without one) answers {@code "unknown"} rather
 * than crashing the filter chain.</p>
 */
@Component("ipKeyResolver")
public class IpKeyResolver implements KeyResolver {

    static final String UNKNOWN = "unknown";

    @Override
    public Mono<String> resolve(ServerWebExchange exchange) {
        InetSocketAddress address = exchange.getRequest().getRemoteAddress();
        if (address == null || address.getAddress() == null) {
            return Mono.just(UNKNOWN);
        }
        return Mono.just(address.getAddress().getHostAddress());
    }
}
