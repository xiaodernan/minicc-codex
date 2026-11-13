package com.minicc.cloud.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.web.server.ServerWebExchange;
import reactor.test.StepVerifier;

import java.net.InetSocketAddress;

/**
 * The rate-limit key is the caller's IP. A front door meters by client, never
 * by path or user-agent; a missing socket address degrades to a shared
 * bucket ("unknown") instead of crashing the chain — one misbehaving client
 * just shares that bucket with the health probes.
 */
class IpKeyResolverTest {

    private final IpKeyResolver resolver = new IpKeyResolver();

    @Test
    void resolvesTheCallersIp() {
        MockServerHttpRequest request = MockServerHttpRequest
                .get("/api/tasks")
                .remoteAddress(new InetSocketAddress("203.0.113.10", 8443))
                .build();
        ServerWebExchange exchange = MockServerWebExchange.from(request);

        StepVerifier.create(resolver.resolve(exchange))
                .expectNext("203.0.113.10")
                .verifyComplete();
    }

    @Test
    void nullAddressDegradesToASharedBucket() {
        MockServerHttpRequest request = MockServerHttpRequest.get("/api/tasks").build();
        ServerWebExchange exchange = MockServerWebExchange.from(request);

        StepVerifier.create(resolver.resolve(exchange))
                .expectNext("unknown")
                .verifyComplete();
    }
}
