package com.minicc.cloud.bridge;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * The acceptance test for the governor: a burst of identical questions must cost
 * one interpreter, and a later separate question must cost another.
 *
 * <p>This runs a real Python child rather than a delegate, because the thing
 * being counted - how many processes the host was asked to start - only exists
 * in the process boundary. The child appends one line to a trail file each time
 * it starts, so the trail is the number of interpreters that ran.
 */
class BridgedBurstTest {

    private static final String PYTHON = System.getProperty("minicc.python", "python");
    private static final Duration BUDGET = Duration.ofSeconds(30);

    @Test
    void eightCallersCostOneInterpreterAndTheNextCallCostsAnother(@TempDir Path repo) throws Exception {
        Path trail = repo.resolve("runs.log");
        String script = String.join("\n",
                "import sys, time",
                "open(sys.argv[1], 'a', encoding='utf-8').write('run\\n')",
                "time.sleep(0.8)",
                "print('{\"ok\": true}')");
        List<String> args = List.of("-c", script, trail.toString());

        MiniccBridge bridge = new MiniccBridge(Path.of(PYTHON), repo, BUDGET);
        GovernedRunner runner = new GovernedRunner(bridge, 4, Duration.ofSeconds(20));

        int callers = 8;
        CountDownLatch arrived = new CountDownLatch(callers);
        ExecutorService pool = Executors.newFixedThreadPool(callers);
        List<BridgeResponse> responses = new ArrayList<>();
        try {
            List<Future<BridgeResponse>> futures = new ArrayList<>();
            for (int i = 0; i < callers; i++) {
                futures.add(pool.submit(() -> {
                    arrived.countDown();
                    return runner.run(args);
                }));
            }
            assertThat(arrived.await(10, TimeUnit.SECONDS)).isTrue();
            for (Future<BridgeResponse> future : futures) {
                responses.add(future.get(60, TimeUnit.SECONDS));
            }
        } finally {
            pool.shutdownNow();
        }

        assertThat(responses).hasSize(callers);
        assertThat(responses).allSatisfy(response -> {
            assertThat(response.succeeded()).isTrue();
            assertThat(response.stdout()).contains("\"ok\"");
        });
        assertThat(Files.readAllLines(trail)).as("one interpreter for one question").hasSize(1);
        assertThat(runner.inFlight()).isZero();

        // Coalescing is not caching: the next request must really run again,
        // otherwise a stale workspace answer would be served forever.
        assertThat(runner.run(args).succeeded()).isTrue();
        assertThat(Files.readAllLines(trail)).as("a later question runs again").hasSize(2);
    }
}
