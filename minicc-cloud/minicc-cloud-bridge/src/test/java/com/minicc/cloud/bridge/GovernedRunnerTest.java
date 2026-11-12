package com.minicc.cloud.bridge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.Test;

/**
 * The governor's two policies, tested against a delegate rather than a process.
 *
 * <p>What has to hold: two callers share a child only when they asked the same
 * question; a burst never exceeds the process budget; a caller that cannot get a
 * slot is told so instead of receiving an empty answer; and a failed command does
 * not stay in the dedupe map where it would refuse every later caller.
 */
class GovernedRunnerTest {

    private static BridgeResponse ok(String stdout) {
        return new BridgeResponse(0, stdout, "", false, null, Duration.ofMillis(1));
    }

    @Test
    void identicalConcurrentCommandsShareOneChild() throws Exception {
        AtomicInteger runs = new AtomicInteger();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CommandRunner slow = args -> {
            runs.incrementAndGet();
            entered.countDown();
            await(release);
            return ok("shared");
        };
        GovernedRunner runner = new GovernedRunner(slow, 4, Duration.ofSeconds(5));
        List<String> question = List.of("-c", "same-question");

        AtomicReference<BridgeResponse> leaderResult = new AtomicReference<>();
        Thread leader = new Thread(() -> leaderResult.set(runner.run(question)), "leader");
        leader.start();
        assertThat(entered.await(5, TimeUnit.SECONDS)).isTrue();

        // Each follower is started and then observed to be parked in get(), so
        // the sharing assertion cannot be satisfied by a follower that simply ran
        // after the leader had already finished.
        List<Thread> followers = new ArrayList<>();
        List<AtomicReference<BridgeResponse>> followerResults = new ArrayList<>();
        for (int i = 0; i < 7; i++) {
            AtomicReference<BridgeResponse> slot = new AtomicReference<>();
            Thread follower = new Thread(() -> slot.set(runner.run(question)), "follower-" + i);
            follower.start();
            awaitUntil(() -> follower.getState() == Thread.State.WAITING, 5);
            followers.add(follower);
            followerResults.add(slot);
        }
        release.countDown();

        join(leader);
        followers.forEach(GovernedRunnerTest::join);
        assertThat(leaderResult.get().stdout()).isEqualTo("shared");
        for (AtomicReference<BridgeResponse> slot : followerResults) {
            assertThat(slot.get().stdout()).isEqualTo("shared");
        }
        assertThat(runs.get()).as("one interpreter for one question").isEqualTo(1);
    }

    @Test
    void differentCommandsDoNotShareAnAnswer() {
        AtomicInteger runs = new AtomicInteger();
        CommandRunner counting = args -> {
            runs.incrementAndGet();
            return ok(String.join(",", args));
        };
        GovernedRunner runner = new GovernedRunner(counting, 4, Duration.ofSeconds(1));

        assertThat(runner.run(List.of("-c", "a")).stdout()).isEqualTo("-c,a");
        assertThat(runner.run(List.of("-c", "b")).stdout()).isEqualTo("-c,b");
        assertThat(runs.get()).isEqualTo(2);
    }

    @Test
    void anArgumentThatLooksLikeTwoCannotForgeAnotherCommand() {
        AtomicInteger runs = new AtomicInteger();
        CommandRunner counting = args -> {
            runs.incrementAndGet();
            return ok(String.valueOf(args.size()));
        };
        GovernedRunner runner = new GovernedRunner(counting, 4, Duration.ofSeconds(1));

        assertThat(runner.run(List.of("a", "b")).stdout()).isEqualTo("2");
        assertThat(runner.run(List.of("a\u0000b")).stdout()).isEqualTo("1");
        assertThat(runs.get()).isEqualTo(2);
    }

    @Test
    void aBurstNeverExceedsTheProcessBudget() throws Exception {
        AtomicInteger live = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        CommandRunner slow = args -> {
            peak.accumulateAndGet(live.incrementAndGet(), Math::max);
            sleep(150);
            live.decrementAndGet();
            return ok("done");
        };
        GovernedRunner runner = new GovernedRunner(slow, 2, Duration.ofSeconds(10));

        int callers = 6;
        ExecutorService pool = Executors.newFixedThreadPool(callers);
        try {
            List<Future<BridgeResponse>> results = new ArrayList<>();
            for (int i = 0; i < callers; i++) {
                String distinct = "command-" + i;
                results.add(pool.submit(() -> runner.run(List.of("-c", distinct))));
            }
            for (Future<BridgeResponse> future : results) {
                assertThat(future.get(10, TimeUnit.SECONDS).succeeded()).isTrue();
            }
        } finally {
            pool.shutdownNow();
        }
        assertThat(peak.get()).as("two slots, never three").isEqualTo(2);
    }

    @Test
    void aCallerThatCannotGetASlotIsToldSoInsteadOfGettingAnEmptyAnswer() throws Exception {
        CommandRunner slow = args -> {
            sleep(1500);
            return ok("late");
        };
        GovernedRunner runner = new GovernedRunner(slow, 1, Duration.ofMillis(100));

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<BridgeResponse> holder = pool.submit(() -> runner.run(List.of("-c", "occupies-the-slot")));
            awaitUntil(() -> runner.freeSlots() == 0, 5);

            BridgeResponse refused = runner.run(List.of("-c", "wants-a-slot"));

            assertThat(refused.succeeded()).isFalse();
            assertThat(refused.failureReason()).contains("no process slot became free");
            assertThat(holder.get(10, TimeUnit.SECONDS).succeeded()).isTrue();
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void aFailedCommandDoesNotStayInTheDedupeMap() {
        AtomicInteger runs = new AtomicInteger();
        CommandRunner flaky = args -> {
            if (runs.incrementAndGet() == 1) {
                throw new IllegalStateException("the first child died");
            }
            return ok("second");
        };
        GovernedRunner runner = new GovernedRunner(flaky, 2, Duration.ofSeconds(1));

        assertThatThrownBy(() -> runner.run(List.of("-c", "x")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("the first child died");
        assertThat(runner.inFlight()).isZero();
        assertThat(runner.run(List.of("-c", "x")).stdout()).isEqualTo("second");
    }

    @Test
    void aNegativeBudgetIsRejectedAtConstruction() {
        assertThatThrownBy(() -> new GovernedRunner(args -> ok(""), 0, Duration.ofSeconds(1)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("at least one process slot");
        assertThatThrownBy(() -> new GovernedRunner(args -> ok(""), 1, Duration.ZERO))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("a positive wait");
    }

    private static void awaitUntil(BooleanSupplier condition, int seconds) {
        long deadline = System.nanoTime() + Duration.ofSeconds(seconds).toNanos();
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            sleep(10);
        }
        throw new AssertionError("condition did not hold within " + seconds + "s");
    }

    private static void join(Thread thread) {
        try {
            thread.join(10_000);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
        }
    }
}
