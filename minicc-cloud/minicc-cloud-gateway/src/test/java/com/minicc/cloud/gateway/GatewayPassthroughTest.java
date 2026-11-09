package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

/**
 * What crosses the gateway hop, measured against a real HTTP downstream.
 *
 * <p>The shipped route is used verbatim: only the instance list behind
 * {@code lb://minicc-cloud-inspector} is a test double, so the load balancer,
 * the CircuitBreaker filter and the fallback are all the ones the YAML names.
 * A gateway that "helpfully" normalises a partial answer into a clean one is
 * the defect this class exists to catch.
 */
@SpringBootTest(
        classes = GatewayApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"eureka.client.enabled=false"})
class GatewayPassthroughTest {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final AtomicReference<String> MODE = new AtomicReference<>("partial");
    private static final AtomicReference<String> RECEIVED = new AtomicReference<>("");
    private static final HttpServer STUB = start();

    private static final String PARTIAL_BODY =
            "{\"files\":[],\"total_files\":0,\"partial\":true,"
                    + "\"reasons\":[\"status_read_error: git status could not be read\"]}";

    @Autowired private WebTestClient client;

    @DynamicPropertySource
    static void theOnlyInspectorInstance(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.discovery.client.simple.instances.minicc-cloud-inspector[0].uri",
                () -> "http://127.0.0.1:" + STUB.getAddress().getPort());
    }

    @BeforeEach
    void reset() {
        RECEIVED.set("");
    }

    @AfterAll
    static void stopTheStub() {
        STUB.stop(0);
    }

    /**
     * Zero files beside {@code partial:true} is not a clean workspace. The
     * gateway must carry both halves across, not drop the one that hurts.
     */
    @Test
    void aPartialAnswerKeepsItsFlagAndItsReasonAcrossTheGateway() throws Exception {
        MODE.set("partial");

        Map<String, Object> body = get(200, "/api/changes", "D:/some/workspace");

        assertThat(body.get("partial")).isEqualTo(Boolean.TRUE);
        assertThat(body.get("total_files")).isEqualTo(0);
        assertThat(body.get("files")).isEqualTo(java.util.List.of());
        assertThat(String.valueOf(body.get("reasons"))).contains("status_read_error");
    }

    /** A refusal is the inspector's answer, not a transport failure. */
    @Test
    void aRefusedWorkspaceKeepsIts403InsteadOfBecomingAFallback() throws Exception {
        MODE.set("refused");

        Map<String, Object> body = get(403, "/api/changes", "/outside/the/roots");

        assertThat(body.get("error")).isEqualTo("workspace-refused");
        assertThat(body).doesNotContainKey("files");
    }

    /** The inspector's own 503 already carries a reason; do not replace it. */
    @Test
    void anInspectorThatSaysItIsUnavailableKeepsItsOwnReason() throws Exception {
        MODE.set("unavailable");

        Map<String, Object> body = get(503, "/api/changes", "D:/some/workspace");

        assertThat(body.get("error")).isEqualTo("minicc-unavailable");
    }

    @Test
    void aDownstreamThatClosesWithoutAnsweringIsAFallbackWithAReason() throws Exception {
        MODE.set("close");

        Map<String, Object> body = get(503, "/api/changes", "D:/some/workspace");

        assertThat(body.get("error")).isEqualTo("inspector-unavailable");
        assertThat(String.valueOf(body.get("reason"))).contains("not an empty change list");
        assertThat(body).doesNotContainKey("files");
        assertThat(body).doesNotContainKey("total_files");
    }

    /** The workspace a caller named must arrive decoded, not mojibake. */
    @Test
    void aWorkspaceNamedInChineseReachesTheInspectorIntact() throws Exception {
        MODE.set("partial");
        String workspace = "D:/面试项目/notes.md";

        get(200, "/api/changes", workspace);

        String seen = RECEIVED.get();
        assertThat(java.net.URLDecoder.decode(seen, StandardCharsets.UTF_8))
                .contains(workspace);
    }

    @Test
    void theDiffQueryKeepsBothOfItsParameters() throws Exception {
        MODE.set("partial");

        client.get()
                .uri(builder ->
                        builder.path("/api/changes/diff")
                                .queryParam("workspace", "D:/some/workspace")
                                .queryParam("path", "src/a.txt")
                                .build())
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus()
                .isOk();

        assertThat(RECEIVED.get()).contains("path=src");
        assertThat(RECEIVED.get()).contains("workspace=");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> get(int status, String path, String workspace) throws IOException {
        byte[] raw =
                client.get()
                        .uri(builder ->
                                builder.path(path).queryParam("workspace", workspace).build())
                        .accept(MediaType.APPLICATION_JSON)
                        .exchange()
                        .expectStatus()
                        .isEqualTo(status)
                        .expectHeader()
                        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                        .expectBody()
                        .returnResult()
                        .getResponseBody();
        assertThat(raw).isNotNull();
        return JSON.readValue(raw, Map.class);
    }

    private static HttpServer start() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", GatewayPassthroughTest::answer);
            server.start();
            return server;
        } catch (IOException cause) {
            throw new IllegalStateException("the stub inspector could not bind a port", cause);
        }
    }

    private static void answer(HttpExchange exchange) throws IOException {
        RECEIVED.set(exchange.getRequestURI().toString());
        String mode = MODE.get();
        if ("close".equals(mode)) {
            exchange.close();
            return;
        }
        int status =
                switch (mode) {
                    case "refused" -> 403;
                    case "unavailable" -> 503;
                    default -> 200;
                };
        String body =
                switch (mode) {
                    case "refused" ->
                            "{\"error\":\"workspace-refused\",\"reason\":\"outside allowed roots\"}";
                    case "unavailable" ->
                            "{\"error\":\"minicc-unavailable\",\"reason\":\"python could not be read\"}";
                    default -> PARTIAL_BODY;
                };
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}