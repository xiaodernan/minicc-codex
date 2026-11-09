package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.config.GatewayProperties;
import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

/**
 * The body limit is enforced by the shipped route, not by a test-local copy.
 *
 * <p>Both halves are asserted: that each route really carries the filter with
 * the configured byte count, and that a body over it is answered 413 without
 * being forwarded. The route definition alone could be green while the filter
 * name was misspelled and bound to nothing, so the HTTP call is the control.
 */
@SpringBootTest(
        classes = GatewayApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "eureka.client.enabled=false",
            "spring.cloud.discovery.enabled=false",
            "spring.cloud.discovery.reactive.enabled=false"
        })
class GatewayRequestSizeTest {

    private static final int LIMIT = 1048576;

    @Autowired private GatewayProperties properties;
    @Autowired private WebTestClient client;

    @Test
    void bothRoutesNameTheRequestSizeFilterWithTheConfiguredLimit() {
        for (String id : List.of("inspector-changes", "tasks")) {
            List<FilterDefinition> matching = route(id).getFilters().stream()
                    .filter(filter -> "RequestSize".equals(filter.getName()))
                    .toList();
            assertThat(matching).hasSize(1);
            assertThat(matching.get(0).getArgs()).containsEntry("maxSize", String.valueOf(LIMIT));
        }
    }

    @Test
    void aBodyOneByteOverTheLimitIsA413AndIsNeverForwarded() {
        byte[] body = new byte[LIMIT + 1];

        client.post()
                .uri("/api/changes?workspace=/tmp/whatever")
                .contentType(MediaType.APPLICATION_JSON)
                .contentLength(body.length)
                .bodyValue(body)
                .exchange()
                .expectStatus()
                .isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE)
                .expectHeader()
                .exists("errorMessage");
    }

    private RouteDefinition route(String id) {
        return properties.getRoutes().stream()
                .filter(route -> id.equals(route.getId()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("route " + id + " is missing"));
    }
}
