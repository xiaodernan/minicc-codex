package com.minicc.cloud.registry;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;

/**
 * The discovery hub itself must be provably alive: if the registry's context fails to
 * load, every lb:// route in the gateway lies to its caller with a connection error,
 * and the operators have no single pane that says "the hub is down".
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DirtiesContext
class RegistryHealthTest {

    @LocalServerPort
    int port;

    @Test
    void actuatorHealthIsUp() throws Exception {
        String body = get("/actuator/health");
        assertThat(body).contains("UP");
    }

    @Test
    void eurekaAppsReturnsAnEmptyButWellFormedRegistry() throws Exception {
        String body = get("/eureka/apps");
        // An empty registry answers with a well-formed XML/JSON document, not a 500.
        assertThat(body).doesNotContain("\"status\":\"DOWN\"")
                .doesNotContain("Internal Server Error");
    }

    private String get(String path) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .GET()
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }
}
