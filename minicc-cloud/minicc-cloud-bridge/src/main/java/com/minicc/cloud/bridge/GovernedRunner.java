package com.minicc.cloud.bridge;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

/**
 * Bounds how many Python children may exist at once and folds identical
 * concurrent commands into a single child.
 *
 * <p>Two costs live at this boundary and nowhere else. Every inspection starts a
 * fresh interpreter, so a burst of N HTTP requests used to start N interpreters
 * competing for the same cores. And when a page polls two panels that ask the
 * same question, each poll paid twice for one answer.
 *
 * <p>Neither policy is allowed to change an answer. A caller either receives the
 * reply of the child that ran its <em>exact</em> command - the coalescing key is
 * the full argv, so two callers can only share a child when they asked the same
 * question - or a failure naming why it did not run. A slot that never frees up
 * is reported as a failure, never as an empty result, because an empty change
 * list reads as "this workspace is clean".
 */
public final class GovernedRunner implements CommandRunner {

    private final CommandRunner delegate;
    private final Semaphore permits;
    private final Duration maxWait;
    private final Map<String, CompletableFuture<BridgeResponse>> inFlight = new ConcurrentHashMap<>();

    /**
     * @param delegate  the real boundary, usually {@link MiniccBridge}
     * @param permits   how many children may run at once; at least one
     * @param maxWait   how long a caller may queue for a slot before it is told
     *                  the boundary is saturated
     */
    public GovernedRunner(CommandRunner delegate, int permits, Duration maxWait) {
        if (delegate == null) {
            throw new IllegalArgumentException("a delegate is required");
        }
        if (permits < 1) {
            throw new IllegalArgumentException("at least one process slot is required, got " + permits);
        }
        if (maxWait == null || maxWait.isNegative() || maxWait.isZero()) {
            throw new IllegalArgumentException("a positive wait is required, got " + maxWait);
        }
        this.delegate = delegate;
        this.permits = new Semaphore(permits);
        this.maxWait = maxWait;
    }

    @Override
    public BridgeResponse run(List<String> args) {
        String key = key(args);
        CompletableFuture<BridgeResponse> mine = new CompletableFuture<>();
        CompletableFuture<BridgeResponse> leader = inFlight.putIfAbsent(key, mine);
        if (leader != null) {
            // Someone is already paying for exactly this question. Share the
            // answer instead of starting a second interpreter to ask it again.
            return follow(leader);
        }
        try {
            BridgeResponse response = runBounded(args);
            mine.complete(response);
            return response;
        } catch (RuntimeException | Error exc) {
            mine.completeExceptionally(exc);
            throw exc;
        } finally {
            inFlight.remove(key, mine);
        }
    }

    /** How many commands are being served right now (leaders, not followers). */
    public int inFlight() {
        return inFlight.size();
    }

    /** How many process slots are free right now. */
    public int freeSlots() {
        return permits.availablePermits();
    }

    private BridgeResponse runBounded(List<String> args) {
        boolean acquired;
        try {
            acquired = permits.tryAcquire(maxWait.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            return failure("interrupted while waiting for a free process slot");
        }
        if (!acquired) {
            return failure("no process slot became free within " + maxWait
                    + "; every slot was busy with another inspection");
        }
        try {
            return delegate.run(args);
        } finally {
            permits.release();
        }
    }

    private BridgeResponse follow(CompletableFuture<BridgeResponse> leader) {
        try {
            return leader.get();
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            return failure("interrupted while waiting for an identical command already in flight");
        } catch (ExecutionException exc) {
            Throwable cause = exc.getCause();
            if (cause instanceof RuntimeException runtime) {
                throw runtime;
            }
            if (cause instanceof Error error) {
                throw error;
            }
            return failure("the shared command failed: " + cause);
        }
    }

    private static BridgeResponse failure(String reason) {
        return new BridgeResponse(-1, "", "", false, reason, Duration.ZERO);
    }

    /**
     * The coalescing key is the whole argv, encoded prefix-free.
     *
     * <p>A plain delimiter join is not enough: {@code ["a", "b"]} and
     * {@code ["a\u0000b"]} would encode alike and two different questions would
     * share one child. Length prefixes make the encoding injective, so sharing
     * only ever happens between callers that asked the same question.
     */
    private static String key(List<String> args) {
        StringBuilder encoded = new StringBuilder();
        for (String arg : args) {
            encoded.append(arg.length()).append(':').append(arg);
        }
        return encoded.toString();
    }
}
