package com.minicc.cloud.gateway;

import reactor.core.publisher.Mono;

/** One upstream health reading, whatever its shape after normalisation. */
public record UpstreamHealth(String status) {}
