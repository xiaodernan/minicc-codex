package com.minicc.cloud.gateway;

import reactor.core.publisher.Mono;

/** Outbound health probe against one Eureka-discovered upstream. */
public interface UpstreamHealthProbe {
    /** Probe {@code service}'s actuator health endpoint via client-side load balancing. */
    Mono<UpstreamHealth> probe(String service);
}
