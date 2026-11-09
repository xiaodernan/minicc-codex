package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

/**
 * P1's promise: the gateway's timeouts are not two literals that happen to
 * agree, they are one key from the config server.
 *
 * <p>Both consumers are asserted in the same test on purpose — the HTTP
 * client's response timeout and the circuit breaker's time limiter. A batch
 * that moved only one of them would leave the other discarding answers the
 * first was still waiting for, and a single-key assertion could not see it.
 */
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "minicc.cloud.gateway.response-timeout-seconds=5")
class TheTwoTimeoutsFollowOneKeyTest {

    @Autowired
    private Environment env;

    @Test
    void bothTimeoutsReadTheConfiguredSeconds() {
        assertThat(env.getProperty("spring.cloud.gateway.server.webflux.httpclient.response-timeout"))
                .isEqualTo("5s");
        assertThat(env.getProperty("resilience4j.timelimiter.instances.inspector-route.timeout-duration"))
                .isEqualTo("5s");
    }
}
