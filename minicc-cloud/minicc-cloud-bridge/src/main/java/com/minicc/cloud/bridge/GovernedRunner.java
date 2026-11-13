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
        this(delegate, permits, maxWait, DEFAULT_MAX_ATTEMPTS, DEFAULT_RETRY_DELAY);
    }

    /**
     * Extended constructor:  limits how many times a transient delegate failure is retried.
     *
     * <p>A volatile subprocess (Python child that crashes, OOM-killed, or the pipe
     * closes) must not permanently take the bridge offline: the boundary retries up to
     * {@code maxAttempts} attempts in total before the caller sees a failure, always
     * preserving {@code permits} for the actual child processes.
     */
    public GovernedRunner(CommandRunner delegate, int permits, Duration maxWait,
                          int maxAttempts, Duration retryDelay) {
        if (delegate == null) {
            throw new IllegalArgumentException("a delegate is required");
        }
        if (permits < 1) {
            throw new IllegalArgumentException("at least one process slot is required, got " + permits);
        }
        if (maxWait == null || maxWait.isNegative() || maxWait.isZero()) {
            throw new IllegalArgumentException("a positive wait is required, got " + maxWait);
        }
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("at least one attempt is required, got " + maxAttempts);
        }
        if (retryDelay == null || retryDelay.isNegative()) {
            throw new IllegalArgumentException("a non-negative retry delay is required");
        }
        this.delegate = delegate;
        this.permits = new Semaphore(permits);
        this.maxWait = maxWait;
        this.maxAttempts = maxAttempts;
        this.retryDelay = retryDelay;
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

    /** Default attempts for a volatile transient delegate failure (3 = 1 + 2 retries). */
    public static final int DEFAULT_MAX_ATTEMPTS = 3;
    public static final Duration DEFAULT_RETRY_DELAY = Duration.ofMillis(150);

    private final int maxAttempts;
    private final Duration retryDelay;

    private BridgeResponse runBounded(List<String> args) {
        for (int attempt = 1; ; attempt++) {
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
                try {
                    return delegate.run(args);
                } finally {
                    permits.release();
                }
            } catch (RuntimeException exc) {
                // The MiniccBridge surfaces real child failures (non-zero exit,
                // timeout, interrupt, broken pipe) inside BridgeResponse, never as
                // an exception. Only the volatile, retry-worthy exceptions escape
                // — even so, the last attempt always runs to completion and surfaces
                // any persistent failure rather than masking it.
                if (attempt >= maxAttempts) {
                    throw exc;
                }
                sleep(retryDelay);
            }
        }
    }

    private void sleep(Duration d) {
        try {
            Thread.sleep(d.toMillis());
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
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
