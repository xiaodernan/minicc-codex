package com.minicc.cloud.gateway;

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
    @Bean
    public WebClient upstreamWebClient(ReactorLoadBalancerExchangeFilterFunction loadBalancerExchangeFilter) {
        return WebClient.builder().filter(loadBalancerExchangeFilter).build();
    }

    @Bean
    public UpstreamHealthProbe upstreamHealthProbe(WebClient upstreamWebClient) {
        return new HttpUpstreamHealthProbe(upstreamWebClient);
    }
}
