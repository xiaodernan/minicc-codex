package com.minicc.cloud.bridge;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * A script must reach the child exactly as the caller wrote it.
 *
 * <p>On Windows the JDK quotes a child argument but does not escape a double
 * quote inside it, so MSVCRT ends the quoted run at the inner quote and the
 * child runs a different program. The failure is silent: exit code 0, plausible
 * output, wrong answer. These tests pin the delivery rule that prevents it.
 */
class BridgeScriptDeliveryTest {

    private static final String PYTHON = System.getProperty("minicc.python", "python");
    private static final Duration BUDGET = Duration.ofSeconds(20);

    @TempDir Path repo;

    @Test
    void aScriptWithDoubleQuotesReachesTheChildByteForByte() {
        // The double quotes are in the script's own source, not produced by
        // json.dumps: this is the payload that the Windows command line cannot
        // carry, and a test that generates its quotes at runtime would never
        // exercise the delivery rule.
        String script = String.join("\n",
                "import json, sys",
                "print(json.dumps({\"ok\": True, \"argv\": sys.argv[1:]}, ensure_ascii=False))");
        MiniccBridge bridge = new MiniccBridge(Path.of(PYTHON), repo, BUDGET);

        // The arguments are the shapes this boundary actually carries: a
        // workspace path and a repo-relative path. A Windows path cannot contain
        // a double quote, and POSIX passes argv without a quoting layer, so the
        // script body is the only place a quote can appear.
        BridgeResponse response = bridge.run(List.of("-c", script, "a b", "c:d"));

        assertThat(response.succeeded()).isTrue();
        assertThat(response.stdout())
                .as("the quote survived inside the script")
                .contains("\"ok\": true");
        assertThat(response.stdout())
                .as("argv indexing is unchanged: -c and - both occupy argv[0]")
                .contains("\"a b\"")
                .contains("\"c:d\"");
    }

    @Test
    void aScriptWithoutDoubleQuotesKeepsItsOldPath() {
        MiniccBridge bridge = new MiniccBridge(Path.of(PYTHON), repo, BUDGET);

        BridgeResponse response = bridge.run(List.of("-c", "print('plain')"));

        assertThat(response.succeeded()).isTrue();
        assertThat(response.stdout().strip()).isEqualTo("plain");
    }

    @Test
    void aScriptThatOnlyLooksLikeACommandIsStillJustAScript() {
        // No "-c" prefix: the bridge must not reinterpret an ordinary argument.
        MiniccBridge bridge = new MiniccBridge(Path.of(PYTHON), repo, BUDGET);

        BridgeResponse response = bridge.run(List.of("--version"));

        assertThat(response.succeeded()).isTrue();
        assertThat(response.stdout()).containsIgnoringCase("python");
    }
}
