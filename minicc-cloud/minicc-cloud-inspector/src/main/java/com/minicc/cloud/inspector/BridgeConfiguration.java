package com.minicc.cloud.inspector;

import com.minicc.cloud.bridge.CapabilitiesClient;
import com.minicc.cloud.bridge.ChangeInspectorClient;
import com.minicc.cloud.bridge.CommandRunner;
import com.minicc.cloud.bridge.GovernedRunner;
import com.minicc.cloud.bridge.MiniccBridge;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.nio.file.Path;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BridgeConfiguration {

    /**
     * One governed boundary per service, shared by every client.
     *
     * <p>The process budget belongs to the host, not to a client: a per-client
     * allowance would multiply the number of interpreters a burst can start,
     * which is the very cost this exists to cap. The wait is the inspection
     * budget plus a small margin, so a caller that queues behind a slow child is
     * told the boundary is saturated a little after that child would have timed
     * out on its own.
     */
    @Bean
    CommandRunner miniccCommands(MiniccProperties properties,
            @org.springframework.beans.factory.annotation.Value("${minicc.cloud.bridge.max-attempts:3}") int maxAttempts,
            @org.springframework.beans.factory.annotation.Value("${minicc.cloud.bridge.retry-delay-ms:150}") long retryDelayMs) {
        MiniccBridge bridge = new MiniccBridge(
                Path.of(properties.python()), Path.of(properties.repo()), properties.budget());
        return new GovernedRunner(bridge, properties.maxProcesses(), properties.budget().plusSeconds(5),
                maxAttempts, Duration.ofMillis(retryDelayMs));
    }

    @Bean
    ChangeInspectorClient changeInspectorClient(CommandRunner commands) {
        return new ChangeInspectorClient(commands);
    }

    @Bean
    CapabilitiesClient capabilitiesClient(CommandRunner commands) {
        return new CapabilitiesClient(commands);
    }

    /**
     * The Python child is a dependency that can stall, so it gets a breaker.
     * An open breaker is reported as a failure with a reason - never as an empty
     * change list, which would read as "this workspace is clean".
     */
    @Bean
    CircuitBreaker miniccCircuitBreaker() {
        return CircuitBreaker.of("minicc-python", CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .failureRateThreshold(50f)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build());
    }
}