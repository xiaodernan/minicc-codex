package com.minicc.cloud.bridge;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * A Python child can echo the environment it was handed: an exception traceback
 * naming {@code MINICC_API_KEY}, or a library that prints a request's
 * {@code Authorization} header. That text travels through the bridge into HTTP
 * responses and logs, so it must be redacted at the boundary once - not by every
 * caller that happens to render a failure.
 */
class BridgeStderrRedactionTest {

    private static final String PYTHON = System.getProperty("minicc.python", "python");
    private static final Duration BUDGET = Duration.ofSeconds(20);

    @TempDir Path repo;

    @Test
    void secretsTheChildEchoesAreRedactedBeforeTheyLeaveTheBridge() {
        String script = String.join("\n",
                "import sys",
                "sys.stderr.write('MINICC_API_KEY=sk-abcdef0123456789\\n')",
                "sys.stderr.write('Authorization: Bearer abc.def.ghi\\n')",
                "sys.stderr.write('the trail could not be opened\\n')",
                "sys.exit(3)");
        MiniccBridge bridge = new MiniccBridge(Path.of(PYTHON), repo, BUDGET);

        BridgeResponse response = bridge.run(List.of("-c", script));

        assertThat(response.succeeded()).isFalse();
        assertThat(response.stderr())
                .contains("[redacted]")
                .doesNotContain("sk-abcdef0123456789")
                .doesNotContain("abc.def.ghi");
        // The failure reason is what reaches the HTTP body and the log line.
        assertThat(response.failureReason())
                .contains("[redacted]")
                .doesNotContain("sk-abcdef0123456789")
                .doesNotContain("abc.def.ghi")
                // Redaction must not cost the operator the reason the child gave.
                .contains("the trail could not be opened");
    }
}
