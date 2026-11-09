package com.minicc.cloud.inspector;

import com.minicc.cloud.bridge.ChangeInspectorClient;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.nio.file.Path;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BridgeConfiguration {

    @Bean
    ChangeInspectorClient changeInspectorClient(MiniccProperties properties) {
        return new ChangeInspectorClient(
                Path.of(properties.python()), Path.of(properties.repo()), properties.budget());
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