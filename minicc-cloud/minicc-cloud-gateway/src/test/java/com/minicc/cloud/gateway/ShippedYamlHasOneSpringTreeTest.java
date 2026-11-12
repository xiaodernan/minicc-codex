package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

/**
 * M8-T822 — the shipped application.yml is one ``spring:`` tree, not two.
 *
 * <p>Before this batch the gateway config had a second top-level {@code spring:}
 * block (for redis/cache/rabbitmq). SnakeYAML rejects a duplicate top-level
 * key outright — the gateway ApplicationContext failed to load with
 * {@code found duplicate key spring}, so all 17 gateway tests errored and a
 * standalone gateway could not start at all. Nothing about the routes was
 * wrong; the file never parsed.
 *
 * <p>This gate is deliberately a plain text scan with no Spring context and no
 * YAML library: it is fast, deterministic, and survives a broken file (a real
 * YAML-based test cannot even load the context to fail meaningfully). It pins
 * two things at once:
 * <ol>
 *   <li>no top-level key appears twice (the general invariant), and</li>
 *   <li>the merge did not lose a key: the routes and the three redis/cache/rabbit
 *       blocks still live under the single {@code spring:} tree.</li>
 * </ol>
 */
class ShippedYamlHasOneSpringTreeTest {

    private static final Path YAML =
            Path.of("src", "main", "resources", "application.yml");

    /** A top-level key: column 0, a bare key, a colon. Not a list item, not nested. */
    private static List<String> topLevelKeys(List<String> lines) {
        List<String> keys = new ArrayList<>();
        for (String line : lines) {
            if (line.isEmpty() || line.charAt(0) == ' ' || line.charAt(0) == '#') {
                continue;
            }
            int colon = line.indexOf(':');
            if (colon <= 0) {
                continue;
            }
            keys.add(line.substring(0, colon).trim());
        }
        return keys;
    }

    private static List<String> lines() {
        try {
            return Files.readAllLines(YAML, StandardCharsets.UTF_8);
        } catch (IOException exc) {
            throw new UncheckedIOException(exc);
        }
    }

    @Test
    void noTopLevelKeyIsDeclaredTwice() {
        List<String> keys = topLevelKeys(lines());
        Set<String> seen = new HashSet<>();
        List<String> duplicates = new ArrayList<>();
        for (String key : keys) {
            if (!seen.add(key)) {
                duplicates.add(key);
            }
        }
        assertThat(duplicates)
                .as("a duplicate top-level key makes SnakeYAML refuse the whole file")
                .isEmpty();
        assertThat(keys).contains("spring", "eureka", "management", "resilience4j");
    }

    @Test
    void routesAndCacheKeysSurvivedTheMergeIntoOneSpringTree() {
        String text = String.join("\n", lines());
        // All three gateway routes are still bound.
        for (String route : new String[] {"inspector-changes", "tasks", "insights"}) {
            assertThat(text).as("route %s must survive the spring-tree merge", route).contains("id: " + route);
        }
        // The three blocks that used to be the second spring: are still present
        // as properties of the first one (indented two spaces under `spring:`).
        for (String key : new String[] {"  data:", "  cache:", "  rabbitmq:"}) {
            assertThat(text).as("%s must live inside the single spring: tree", key).contains(key);
        }
        assertThat(text).contains("time-to-live: 60s");
        assertThat(text).contains("cache-names: gateway-routes");
    }
}
