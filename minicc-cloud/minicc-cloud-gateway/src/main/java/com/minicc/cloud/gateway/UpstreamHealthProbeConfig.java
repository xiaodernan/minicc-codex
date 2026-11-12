package com.minicc.cloud.gateway;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.loadbalancer.reactive.ReactorLoadBalancerExchangeFilterFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * Wires the {@code lb://} client: WebFlux needs the load-balancing exchange filter to
 * resolve a service name through Eureka, so {@code lb://minicc-cloud-insights/...}
 * reaches the concrete instance(s) the registry knows about.
 */
@Configuration
public class UpstreamHealthProbeConfig {
    @Value("${minicc.cloud.gateway.probe-timeout-ms:2000}")
    long probeTimeoutMs;

    @Value("${minicc.cloud.gateway.changes-timeout-ms:35000}")
    long changesTimeoutMs;

    @Bean
    public WebClient upstreamWebClient(ReactorLoadBalancerExchangeFilterFunction loadBalancerExchangeFilter) {
        return WebClient.builder().filter(loadBalancerExchangeFilter).build();
    }

    @Bean
    public UpstreamHealthProbe upstreamHealthProbe(WebClient upstreamWebClient) {
        return new HttpUpstreamHealthProbe(upstreamWebClient, Duration.ofMillis(probeTimeoutMs));
    }

    @Bean
    public InspectorChangesProbe inspectorChangesProbe(WebClient upstreamWebClient) {
        return new HttpInspectorChangesProbe(upstreamWebClient, Duration.ofMillis(changesTimeoutMs));
    }
}
