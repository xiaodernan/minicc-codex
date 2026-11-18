package com.minicc.cloud.evidence;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * The HTTP shape: one JSON envelope whether the payload says "facts", admits
 * it has none, or admits it is broken - plus zero ways to be mistaken for a
 * passing run.
 */
class EvidenceControllerTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @TempDir Path temp;

    private Path store;
    private EvidenceFixture.CountingFetcher fetcher;
    private EvidenceService service;

    @BeforeEach
    void setUp() {
        store = EvidenceFixture.storeFile(temp);
        fetcher = new EvidenceFixture.CountingFetcher(EvidenceFixture.entry(99L, "2026-11-18T00:00:00Z", "success"));
        service = new EvidenceService(new EvidenceStore(EvidenceFixture.properties(store)), fetcher);
    }

    private MockMvc mvc() {
        return MockMvcBuilders.standaloneSetup(new EvidenceController(service))
                .setControllerAdvice(new EvidenceFailureAdvice())
                .build();
    }

    private JsonNode answer(String query, int expectedStatus) throws Exception {
        MvcResult result = mvc().perform(get("/api/evidence?" + query))
                .andExpect(status().is(expectedStatus))
                .andReturn();
        return JSON.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    @Test
    void neitherParamIs400() throws Exception {
        answer("", 400);
    }

    @Test
    void bothParamsIs400() throws Exception {
        assertThat(answer("latest=1&run_id=123", 400).get("error").asText()).isEqualTo("request-refused");
    }

    @Test
    void nonNumericRunIdIs400() throws Exception {
        assertThat(answer("run_id=abc123", 400).get("error").asText()).isEqualTo("request-refused");
    }

    @Test
    void latestOfAMissingStoreIs503NeverAGreenLight() throws Exception {
        Path missing = temp.resolve("missing.jsonl");
        service = new EvidenceService(new EvidenceStore(EvidenceFixture.properties(missing)), fetcher);

        JsonNode body = answer("latest=1", 503);

        assertThat(body.get("present").asBoolean()).isFalse();
        assertThat(body.get("error").asText()).isEqualTo("evidence-store-unavailable");
        assertThat(body.toString()).doesNotContain("gh_");
        assertThat(body.toString().toLowerCase()).doesNotContain("token");
    }

    @Test
    void latestOfAnEmptyStoreIs200PresentFalse() throws Exception {
        Files.writeString(store, "", StandardCharsets.UTF_8);

        JsonNode body = answer("latest=1", 200);

        assertThat(body.get("present").asBoolean()).isFalse();
        assertThat(body.get("reason").asText()).contains("no evidence");
        assertThat(fetcher.calls()).isZero();
    }

    @Test
    void run_idBackfillsOnceAndIsHonest() throws Exception {
        Files.writeString(store, "", StandardCharsets.UTF_8);

        JsonNode body = answer("run_id=99", 200);

        assertThat(body.get("present").asBoolean()).isTrue();
        assertThat(fetcher.calls()).isEqualTo(1);
        assertThat(body.get("latest").get("run_id").asLong()).isEqualTo(99);
        assertThat(body.get("latest").get("logs_tail").toString()).contains("line 1");
    }

    @Test
    void run_idCacheHitNeverReachesGitHub() throws Exception {
        Files.writeString(store, "", StandardCharsets.UTF_8);
        answer("run_id=99", 200);
        answer("run_id=99", 200);

        assertThat(fetcher.calls()).as("the second read is the cache, not GitHub").isEqualTo(1);
    }

    @Test
    void run_idBackfillFailureIs503NeverAGreenLight() throws Exception {
        Files.writeString(store, "", StandardCharsets.UTF_8);
        service = new EvidenceService(
                new EvidenceStore(EvidenceFixture.properties(store)), new EvidenceFixture.ExplodingFetcher());

        JsonNode body = answer("run_id=99", 503);

        assertThat(body.get("present").asBoolean()).isFalse();
        assertThat(body.get("error").asText()).isEqualTo("evidence-backfill-failed");
        assertThat(Files.readString(store, StandardCharsets.UTF_8)).isEmpty();
    }
}
