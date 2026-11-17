package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/**
 * M8-T1179 - the config plane's one-fact homes cannot drift.
 *
 * <p>Three invariants, three teeth, no Spring context, no broker, no network:
 *
 * <ol>
 *   <li>Every shipped YAML parses with duplicate keys refused - the M8-T822
 *       class of defect ({@code found duplicate key spring}) is caught at the
 *       first offending mapping, not seventeen red tests later.</li>
 *   <li>Every inline standalone fallback the ymls declare (documented as
 *       exactly that - a standalone fallback, not a second source of truth)
 *       equals the value the config repo serves for the same knob. A drift
 *       between the two spells a silently differing deployment.</li>
 *   <li>Each dotted {@code minicc.cloud.*} key that has a home in config-repo
 *       lives in exactly one config-repo file - the shared value cannot be
 *       copy-pasted into a service-specific file where it silently drifts.</li>
 * </ol>
 *
 * <p>Env-knob placeholders ({@code ${MINICC_TASKS_MAX_LIMIT:100}}) are bound
 * to their config-repo keys through an explicit list below - never through a
 * name-derivation heuristic, because a heuristic silently exempts oddities
 * instead of refusing them.
 */
class ShippedConfigHomesAgreeTest {

    private static final Pattern PLACEHOLDER =
            Pattern.compile("\\$\\{([A-Za-z0-9._-]+):([^}\\n]*)}");

    /**
     * env knob -> dotted config key that must carry the same default.
     * Explicit: a derivation heuristic would bless spellings nobody checked.
     */
    private static final Map<String, String> ENV_KNOB_TO_CONFIG_KEY = Map.of(
            "MINICC_TASKS_MAX_LIMIT", "minicc.cloud.tasks.max-limit",
            "MINICC_INSIGHTS_MAX_SCAN_ROWS", "minicc.cloud.insights.max-scan-rows",
            "MINICC_INSIGHTS_MAX_AUDIT_LINES", "minicc.cloud.insights.max-audit-lines",
            "MINICC_CLOUD_BRIDGE_MAXATTEMPTS", "minicc.cloud.inspector.bridge.max-attempts",
            "MINICC_CLOUD_BRIDGE_RETRYDELAYMS", "minicc.cloud.inspector.bridge.retry-delay-ms");

    private static Path planeRoot() {
        Path dir = Path.of("").toAbsolutePath().normalize();
        for (int i = 0; i < 6 && dir != null; i++) {
            if (Files.isDirectory(dir.resolve("minicc-cloud-bridge"))
                    && Files.isDirectory(dir.resolve("minicc-cloud-config"))) {
                return dir;
            }
            dir = dir.getParent();
        }
        throw new AssertionError(
                "could not locate the minicc-cloud plane root from " + Path.of("").toAbsolutePath());
    }

    private static Path configRepo(Path plane) {
        return plane.resolve("minicc-cloud-config")
                .resolve("src").resolve("main").resolve("resources").resolve("config-repo");
    }

    private static List<Path> shippedYamls(Path plane) throws IOException {
        List<Path> yamls = new ArrayList<>();
        try (var stream = Files.walk(plane, 8)) {
            stream.filter(Files::isRegularFile)
                    .filter(p -> {
                        String normalized = p.toAbsolutePath().normalize().toString()
                                .replace('\\', '/');
                        String name = p.getFileName().toString();
                        return normalized.contains("/src/main/resources/")
                                && !normalized.contains("/config-repo/")
                                && !normalized.contains("/target/")
                                && name.endsWith(".yml");
                    })
                    .forEach(yamls::add);
        }
        return yamls;
    }

    private static List<Path> configRepoYamls(Path plane) throws IOException {
        try (var stream = Files.list(configRepo(plane))) {
            List<Path> files = new ArrayList<>();
            stream.filter(Files::isRegularFile).filter(p -> p.getFileName().toString().endsWith(".yml"))
                    .forEach(files::add);
            return files;
        }
    }

    private static Yaml dupKeyRefuser() {
        LoaderOptions options = new LoaderOptions();
        options.setAllowDuplicateKeys(false);
        return new Yaml(new SafeConstructor(options));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> parseMap(Path file) {
        try {
            Object loaded = dupKeyRefuser().load(Files.readString(file, StandardCharsets.UTF_8));
            if (loaded == null) {
                return Map.of();
            }
            return (Map<String, Object>) loaded;
        } catch (Exception exc) {  // DuplicateKeyException or any parse failure - both are defects here
            throw new AssertionError("unparsable YAML " + file + " -> " + exc, exc);
        }
    }

    private static String normalizeScalar(Object value) {
        if (value == null) {
            return "";
        }
        String text = String.valueOf(value).trim().toLowerCase();
        if (text.length() >= 2
                && ((text.startsWith("\"") && text.endsWith("\""))
                        || (text.startsWith("'") && text.endsWith("'")))) {
            text = text.substring(1, text.length() - 1);
        }
        return text;
    }

    /** Flattens a nested map into dotted paths; list leaves render as raw strings. */
    private static void flatten(String prefix, Map<String, Object> map, Map<String, Object> out) {
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            String path = prefix.isEmpty() ? String.valueOf(entry.getKey())
                    : prefix + "." + entry.getKey();
            Object value = entry.getValue();
            if (value instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> nested = (Map<String, Object>) value;
                flatten(path, nested, out);
            } else {
                out.put(path, value);
            }
        }
    }

    /** The served home of every dotted key: shared application.yml, name-specific wins. */
    private static Map<String, Object> servedConfig(Path plane) throws IOException {
        Map<String, Object> merged = new HashMap<>();
        List<Path> files = new ArrayList<>();
        files.add(configRepo(plane).resolve("application.yml"));
        for (Path file : configRepoYamls(plane)) {
            if (!file.getFileName().toString().equals("application.yml")) {
                files.add(file);
            }
        }
        for (Path file : files) {
            Map<String, Object> flat = new HashMap<>();
            flatten("", parseMap(file), flat);
            merged.putAll(flat);
        }
        return merged;
    }

    @Test
    void allShippedAndConfigRepoYamlsParseWithDuplicateKeysRefused() throws Exception {
        Path plane = planeRoot();
        List<Path> yamls = shippedYamls(plane);
        yamls.addAll(configRepoYamls(plane));
        assertThat(yamls).as("yaml census must not be empty").isNotEmpty();
        List<String> offenders = new ArrayList<>();
        for (Path yaml : yamls) {
            Throwable thrown = catchThrowable(() -> parseMap(yaml));
            if (thrown != null) {
                offenders.add(yaml + " -> " + thrown.getMessage());
            }
        }
        assertThat(offenders).as("duplicate keys are refused by SnakeYAML; none may ship").isEmpty();
    }

    @Test
    void everyInlineFallbackAgreesWithTheConfigRepo() throws Exception {
        Path plane = planeRoot();
        Map<String, Object> served = servedConfig(plane);
        Map<String, String> checked = new HashMap<>();
        for (Path yaml : shippedYamls(plane)) {
            String text = Files.readString(yaml, StandardCharsets.UTF_8);
            Matcher matcher = PLACEHOLDER.matcher(text);
            while (matcher.find()) {
                String path = matcher.group(1);
                String fallback = matcher.group(2).trim();
                if (fallback.contains("{")) {
                    continue;  // nested placeholder default; its innermost key is checked on its own
                }
                String configKey = null;
                if (path.startsWith("minicc.cloud.")) {
                    configKey = path;
                } else if (ENV_KNOB_TO_CONFIG_KEY.containsKey(path)) {
                    configKey = ENV_KNOB_TO_CONFIG_KEY.get(path);
                }
                if (configKey != null && served.containsKey(configKey)) {
                    checked.put(configKey, fallback + " @ " + yaml.getFileName());
                    assertThat(normalizeScalar(fallback))
                            .as("fallback for %s in %s must equal config-repo value", configKey, yaml.getFileName())
                            .isEqualTo(normalizeScalar(served.get(configKey)));
                }
            }
        }
        assertThat(checked).as("the fallbacks under governance must actually be checked, never silently skipped")
                .isNotEmpty();
        assertThat(checked.keySet()).contains(
                "minicc.cloud.gateway.response-timeout-seconds",
                "minicc.cloud.gateway.connect-timeout-ms",
                "minicc.cloud.gateway.max-request-bytes",
                "minicc.cloud.inspector.timeout-seconds",
                "minicc.cloud.tasks.max-limit",
                "minicc.cloud.insights.max-scan-rows",
                "minicc.cloud.insights.max-audit-lines",
                "minicc.cloud.inspector.bridge.max-attempts",
                "minicc.cloud.inspector.bridge.retry-delay-ms");
    }

    @Test
    void eachConfigRepoKeyHasExactlyOneHome() throws Exception {
        Path plane = planeRoot();
        List<Path> files = configRepoYamls(plane);
        assertThat(files).as("config-repo census").isNotEmpty();
        Map<String, List<String>> owners = new HashMap<>();
        for (Path file : files) {
            Map<String, Object> flat = new HashMap<>();
            flatten("", parseMap(file), flat);
            for (String path : flat.keySet()) {
                owners.computeIfAbsent(path, k -> new ArrayList<>()).add(file.getFileName().toString());
            }
        }
        List<String> duplicated = new ArrayList<>();
        for (Map.Entry<String, List<String>> entry : owners.entrySet()) {
            if (new HashSet<>(entry.getValue()).size() > 1) {
                duplicated.add(entry.getKey() + " -> " + String.join(", ", entry.getValue()));
            }
        }
        assertThat(duplicated).as("one dotted key, one file; the drift class the planning doc names").isEmpty();
        assertThat(owners.keySet()).contains(
                "minicc.cloud.inspector.timeout-seconds",
                "minicc.cloud.gateway.response-timeout-seconds",
                "minicc.cloud.tasks.max-limit");
    }
}
