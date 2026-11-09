package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.config.GatewayProperties;
import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionLocator;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

/**
 * The shipped application.yml is the subject here, not a test-local copy of it.
 *
 * <p>A route key under the wrong prefix binds to nothing: the gateway starts
 * green, registers with Eureka, and answers 404 to every call. Only a test that
 * reads the real file catches that, so this class overrides nothing about the
 * routes and asserts the definitions the file actually produced.
 */
@SpringBootTest(
        classes = GatewayApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "eureka.client.enabled=false",
            "spring.cloud.discovery.enabled=false",
            "spring.cloud.discovery.reactive.enabled=false"
        })
class GatewayRouteBindingTest {

    @Autowired private GatewayProperties properties;
    @Autowired private RouteDefinitionLocator locators;
    @Autowired private WebTestClient client;

    @Test
    void theYamlBindsExactlyOneRouteToTheInspectorByServiceName() {
        List<RouteDefinition> routes = properties.getRoutes();
        assertThat(routes).hasSize(1);

        RouteDefinition route = routes.get(0);
        assertThat(route.getId()).isEqualTo("inspector-changes");
        assertThat(route.getUri().toString()).isEqualTo("lb://minicc-cloud-inspector");
    }

    @Test
    void theRouteIsOfferedByTheLocatorAndNotOnlyPresentInTheProperties() {
        List<RouteDefinition> offered =
                locators.getRouteDefinitions().collectList().block();
        assertThat(offered).isNotNull();
        assertThat(offered)
                .extracting(RouteDefinition::getId)
                .contains("inspector-changes");
    }

    @Test
    void theRouteMatchesThePathsTheInspectorServes() {
        List<PredicateDefinition> predicates = properties.getRoutes().get(0).getPredicates();
        assertThat(predicates).hasSize(1);
        assertThat(predicates.get(0).getName()).isEqualTo("Path");
        assertThat(predicates.get(0).getArgs().values())
                .contains("/api/changes", "/api/changes/**");
    }

    @Test
    void theRouteCarriesACircuitBreakerThatForwardsToTheFallback() {
        List<FilterDefinition> filters = properties.getRoutes().get(0).getFilters();
        assertThat(filters).hasSize(1);

        FilterDefinition breaker = filters.get(0);
        assertThat(breaker.getName()).isEqualTo("CircuitBreaker");
        assertThat(breaker.getArgs().values())
                .contains("inspector-route", "forward:/fallback/inspector");
    }

    /**
     * With discovery off there is no instance to resolve, which is the same
     * shape as "the inspector is down". The answer must say so; a 200 carrying
     * an empty file list would claim the workspace is clean.
     */
    @Test
    void anInspectorThatCannotBeResolvedIsA503WithAReasonAndNotAnEmptyChangeList() {
        Map<String, Object> body = answer("/api/changes?workspace=/tmp/whatever");

        assertThat(body.get("error")).isEqualTo("inspector-unavailable");
        assertThat(String.valueOf(body.get("reason"))).isNotBlank();
        assertThat(body).doesNotContainKey("files");
        assertThat(body).doesNotContainKey("total_files");
    }

    @Test
    void theDiffPathIsRoutedTheSameWayAsTheSummaryPath() {
        Map<String, Object> body = answer("/api/changes/diff?workspace=/tmp/whatever&path=a.txt");
        assertThat(body.get("error")).isEqualTo("inspector-unavailable");
    }

    /** A path no route names must stay a 404, not be swept into the fallback. */
    @Test
    void aPathOutsideTheRouteIsNotAnsweredByTheInspectorFallback() {
        client.get()
                .uri("/api/not-the-inspector")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus()
                .isNotFound();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> answer(String uri) {
        return (Map<String, Object>)
                client.get()
                        .uri(uri)
                        .accept(MediaType.APPLICATION_JSON)
                        .exchange()
                        .expectStatus()
                        .isEqualTo(503)
                        .expectBody(Map.class)
                        .returnResult()
                        .getResponseBody();
    }
}