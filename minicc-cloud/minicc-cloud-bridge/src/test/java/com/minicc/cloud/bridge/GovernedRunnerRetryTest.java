package com.minicc.cloud.bridge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

/**
 * M8-T867: the boundary retries volatile delegate exceptions and reports the last
 * one rather than masking it — real child failures (exit codes, timeouts, broken
 * pipes) always surface as {@link BridgeResponse}, never retried.
 */
class GovernedRunnerRetryTest {

    private static final List<String> QUESTION = List.of("-c", "handle");

    @Test
    void volatileDelegateFailuresAreRetriedAndEventuallySurface() {
        AtomicInteger attempts = new AtomicInteger();
        CommandRunner volatileDelegate = args -> {
            if (attempts.incrementAndGet() == 3) {
                throw new IllegalStateException("permanent-stream-closed");
            }
            throw new IllegalStateException("transient #" + attempts.get());
        };

        GovernedRunner runner = new GovernedRunner(volatileDelegate, 1, Duration.ofSeconds(5),
                3, Duration.ofMillis(10));

        assertThatThrownBy(() -> runner.run(QUESTION))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("permanent-stream-closed");
        assertThat(attempts.get()).isEqualTo(3);
    }

    @Test
    void aTransientChainRecoversIntoSuccess() {
        AtomicInteger attempts = new AtomicInteger();
        CommandRunner flaky = args -> {
            int n = attempts.incrementAndGet();
            if (n < 3) {
                throw new IllegalStateException("transient #" + n);
            }
            return new BridgeResponse(0, "served", "", false, null, Duration.ofMillis(1));
        };

        GovernedRunner runner = new GovernedRunner(flaky, 1, Duration.ofSeconds(5),
                3, Duration.ofMillis(10));

        BridgeResponse result = runner.run(QUESTION);
        assertThat(result.exitCode()).isZero();
        assertThat(result.stdout()).isEqualTo("served");
        assertThat(attempts.get()).isEqualTo(3);
    }

    @Test
    void aSingleQuestionIsNotChargedForMoreAttemptsThanItIsOwed() {
        AtomicInteger attempts = new AtomicInteger();
        CommandRunner okDelegate = args -> {
            attempts.incrementAndGet();
            return new BridgeResponse(0, "served", "", false, null, Duration.ofMillis(1));
        };

        GovernedRunner runner = new GovernedRunner(okDelegate, 1, Duration.ofSeconds(5),
                4, Duration.ofMillis(10));

        BridgeResponse result = runner.run(QUESTION);
        assertThat(result.exitCode()).isZero();
        assertThat(attempts.get()).isEqualTo(1);
    }

    @Test
    void aBridgeResponseFailureIsNotRetried() {
        // The bridge never throws; it reports BridgeResponse with exit codes, so a
        // non-zero exit or a timed-out child must surface to the caller exactly once.
        AtomicInteger attempts = new AtomicInteger();
        CommandRunner failing = args -> {
            attempts.incrementAndGet();
            return new BridgeResponse(7, "bad", "", true, "child exited with 7", Duration.ofMillis(1));
        };

        GovernedRunner runner = new GovernedRunner(failing, 1, Duration.ofSeconds(5),
                3, Duration.ofMillis(10));

        BridgeResponse result = runner.run(QUESTION);
        assertThat(result.exitCode()).isEqualTo(7);
        assertThat(attempts.get()).isEqualTo(1);
    }

    @Test
    void permitsAreNotLeakedWhenADelegateThrowsAndIsNotRetriedAgain() {
        // Exhaust retry budget with a throwing delegate, then observe free slots —
        // the semaphore must not be over-drawn by a retried attempt, otherwise the
        // boundary silently becomes a 0-cap bridge after a few bursts.
        CommandRunner alwaysThrows = args -> {
            throw new IllegalStateException("boom");
        };

        GovernedRunner runner = new GovernedRunner(alwaysThrows, 2, Duration.ofSeconds(5),
                2, Duration.ofMillis(10));

        assertThatThrownBy(() -> runner.run(QUESTION))
                .isInstanceOf(IllegalStateException.class);
        assertThat(runner.freeSlots()).isEqualTo(2);
    }
}
