package com.minicc.cloud.bridge;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
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
 * <p>Three rules come straight from the Python side's read-failure batches. The
 * child's stdout and stderr are drained on separate threads, because a child
 * that fills the stderr pipe while the parent only reads stdout blocks forever
 * and the budget then reports a timeout for a program that was merely unheard.
 * And a pipe that could not be read whole is a transport error naming the half,
 * never a silently shorter string that the caller would parse as a small answer.
 * A {@code -c} script whose body contains a double quote travels over stdin
 * instead of the command line, because Windows reconstitutes a child's command
 * line and drops the quote - which silently turns the script into a different
 * program (M8-T841).
 */
public final class MiniccBridge implements CommandRunner {

    private final Path python;
    private final Path repo;
    private final Duration budget;

    public MiniccBridge(Path python, Path repo, Duration budget) {
        this.python = python;
        this.repo = repo;
        this.budget = budget;
    }

    /** Runs {@code python -X utf8 <args>} with the repo as the working directory. */
    @Override
    public BridgeResponse run(List<String> args) {
        byte[] scriptOnStdin = null;
        List<String> effective = args;
        if (needsStdin(args)) {
            // A "-c <script>" whose body contains a double quote cannot travel on
            // a Windows command line: the JDK quotes the argument but does not
            // escape the quote inside it, so MSVCRT closes the quoted run early
            // and the child executes a different program. Measured, not assumed:
            // print('{"ok": true}') arrives as print('{ok: true}'). On stdin the
            // script has no quoting layer at all. "-" and "-c" both occupy
            // argv[0], so every caller's sys.argv[1:] is unchanged.
            scriptOnStdin = args.get(1).getBytes(StandardCharsets.UTF_8);
            effective = new ArrayList<>();
            effective.add("-");
            effective.addAll(args.subList(2, args.size()));
        }

        List<String> command = new ArrayList<>();
        command.add(python.toString());
        command.add("-X");
        command.add("utf8");
        command.addAll(effective);

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
        if (scriptOnStdin != null) {
            feed(process, scriptOnStdin);
        }

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

    /**
     * True for {@code ["-c", script, ...]} whose script contains a double quote.
     *
     * <p>Every other shape keeps its exact current execution path; only a payload
     * that provably cannot survive the Windows command line is rerouted.
     */
    private static boolean needsStdin(List<String> args) {
        return args.size() >= 2 && "-c".equals(args.get(0)) && args.get(1).indexOf('"') >= 0;
    }

    /**
     * Hands the script to the child over its stdin pipe.
     *
     * <p>A child that exited before reading is not a bridge failure: its exit
     * code and stderr already explain what happened, and reporting a broken pipe
     * here would replace that reason with a less useful one.
     */
    private static void feed(Process process, byte[] body) {
        try (OutputStream stdin = process.getOutputStream()) {
            stdin.write(body);
            stdin.flush();
        } catch (IOException ignored) {
            // The child stopped reading; its own exit status carries the reason.
        }
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