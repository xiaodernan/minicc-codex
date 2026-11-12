package com.minicc.cloud.gateway;

import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * Service discovery at work: the gateway asks every upstream it knows about, in parallel,
 * "are you alive?", and answers with one document — the single pane a dashboard or
 * on-call operator needs. Each probe goes through client-side load balancing (Eureka),
 * so a service with two live instances is still one entry in the output.
 */
@RestController
@RequestMapping("/api")
public class AggregateHealthController {

    private static final List<String> SERVICES = List.of(
            "minicc-cloud-inspector",
            "minicc-cloud-tasks",
            "minicc-cloud-insights");

    private final UpstreamHealthProbe probe;

    public AggregateHealthController(UpstreamHealthProbe probe) {
        this.probe = probe;
    }

    @GetMapping("/health/all")
    public Mono<ResponseEntity<Map<String, Object>>> healthAll() {
        return Flux.fromIterable(SERVICES)
                .flatMap(service -> probe.probe(service)
                        .map(health -> Map.of(
                                "service", service,
                                "upstreamStatus", health.status())))
                .collectList()
                .map(AggregateHealthController::buildResponse);
    }

    private static ResponseEntity<Map<String, Object>> buildResponse(List<Map<String, String>> services) {
        long up = services.stream().filter(s -> "UP".equals(s.get("upstreamStatus"))).count();
        return ResponseEntity.ok(Map.of(
                "services", (Object) List.copyOf(services),
                "upCount", up,
                "totalServices", services.size()));
    }
}
