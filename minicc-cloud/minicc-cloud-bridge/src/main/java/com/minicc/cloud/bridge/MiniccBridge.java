package com.minicc.cloud.bridge;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Runs the minicc Python tooling as a child process and reports what came back.
 *
 * <p>Two rules come straight from the Python side's read-failure batches. The
 * child's stdout and stderr are drained on separate threads, because a child
 * that fills the stderr pipe while the parent only reads stdout blocks forever
 * and the budget then reports a timeout for a program that was merely unheard.
 * And a pipe that could not be read whole is a transport error naming the half,
 * never a silently shorter string that the caller would parse as a small answer.
 */
public final class MiniccBridge {

    private final Path python;
    private final Path repo;
    private final Duration budget;

    public MiniccBridge(Path python, Path repo, Duration budget) {
        this.python = python;
        this.repo = repo;
        this.budget = budget;
    }

    /** Runs {@code python -X utf8 <args>} with the repo as the working directory. */
    public BridgeResponse run(List<String> args) {
        List<String> command = new ArrayList<>();
        command.add(python.toString());
        command.add("-X");
        command.add("utf8");
        command.addAll(args);

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(repo.toFile());
        Map<String, String> env = builder.environment();
        // The host is zh_CN Windows. Without these the child writes GBK into a
        // pipe the parent decodes as UTF-8, and every CJK path becomes U+FFFD -
        // which the Python side then treats as a file name (M8-T565).
        env.put("PYTHONIOENCODING", "utf-8");
        env.put("PYTHONUTF8", "1");
        env.put("PYTHONPATH", repo.toString());

        long started = System.nanoTime();
        Process process;
        try {
            process = builder.start();
        } catch (IOException exc) {
            return new BridgeResponse(-1, "", "", false,
                    "could not start " + command.get(0) + ": " + exc, elapsed(started));
        }

        Drain stdout = new Drain(process.getInputStream(), "stdout");
        Drain stderr = new Drain(process.getErrorStream(), "stderr");
        Thread outThread = Thread.ofPlatform().daemon(true).name("minicc-stdout").start(stdout);
        Thread errThread = Thread.ofPlatform().daemon(true).name("minicc-stderr").start(stderr);

        boolean finished;
        try {
            finished = process.waitFor(budget.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException exc) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
            join(outThread, errThread);
            return new BridgeResponse(-1, stdout.text(), stderr.text(), false,
                    "interrupted while waiting for the minicc process", elapsed(started));
        }

        if (!finished) {
            process.destroyForcibly();
            try {
                process.waitFor(5, TimeUnit.SECONDS);
            } catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
            }
            join(outThread, errThread);
            return new BridgeResponse(-1, stdout.text(), stderr.text(), true, null, budget);
        }

        join(outThread, errThread);
        String transport = stdout.error != null ? stdout.error : stderr.error;
        return new BridgeResponse(process.exitValue(), stdout.text(), stderr.text(),
                false, transport, elapsed(started));
    }

    private static Duration elapsed(long startedNanos) {
        return Duration.ofNanos(System.nanoTime() - startedNanos);
    }

    private static void join(Thread... threads) {
        for (Thread thread : threads) {
            try {
                thread.join(TimeUnit.SECONDS.toMillis(5));
            } catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    /** One half of the pipe, drained whole or reported as unread. */
    private static final class Drain implements Runnable {
        private final InputStream stream;
        private final String half;
        private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        private volatile String error;

        Drain(InputStream stream, String half) {
            this.stream = stream;
            this.half = half;
        }

        @Override
        public void run() {
            byte[] chunk = new byte[8192];
            try (InputStream in = stream) {
                int read;
                while ((read = in.read(chunk)) != -1) {
                    buffer.write(chunk, 0, read);
                }
            } catch (IOException exc) {
                error = "could not read the child's " + half + " whole: " + exc;
            }
        }

        String text() {
            return buffer.toString(StandardCharsets.UTF_8);
        }
    }
}