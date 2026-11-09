package com.minicc.cloud.gateway;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

/**
 * What the gateway says when the inspector cannot be reached.
 *
 * <p>The fallback is a 503 with a reason, deliberately not a 200 carrying
 * {@code {"files": [], "total_files": 0}}. An empty list would tell the client
 * the workspace is clean at the exact moment the gateway knows least about it.
 */
@RestController
public class FallbackController {

    @RequestMapping("/fallback/inspector")
    public Mono<ResponseEntity<Map<String, Object>>> inspector() {
        return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "error", "inspector-unavailable",
                        "reason", "the change inspector could not be reached, so nothing is known "
                                + "about this workspace; this is not an empty change list")));
    }
}