package com.minicc.cloud.inspector;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Where the Python tooling lives and what it is allowed to look at.
 *
 * @param python       interpreter to run; the bridge pins its UTF-8 mode itself
 * @param repo         the minicc checkout, used as the child's working directory
 * @param budget       wall time one inspection may spend before it is destroyed
 * @param allowedRoots directories a caller may name as a workspace; empty means
 *                     the repo alone. This is the boundary that stops an HTTP
 *                     caller from reading arbitrary directories off the host.
 * @param maxProcesses how many Python children this service may run at once.
 *                     Unset means the host decides: two, or one per core up to
 *                     eight. It is a service-wide budget, not a per-client one.
 */
@ConfigurationProperties(prefix = "minicc")
public record MiniccProperties(String python, String repo, Duration budget, List<String> allowedRoots,
                               Integer maxProcesses) {

    @org.springframework.boot.context.properties.bind.ConstructorBinding
    public MiniccProperties {
        if (python == null || python.isBlank()) {
            python = "python";
        }
        if (repo == null || repo.isBlank()) {
            repo = ".";
        }
        if (budget == null) {
            budget = Duration.ofSeconds(30);
        }
        if (allowedRoots == null) {
            allowedRoots = List.of();
        }
        if (maxProcesses == null || maxProcesses < 1) {
            maxProcesses = Math.min(8, Math.max(2, Runtime.getRuntime().availableProcessors()));
        }
    }

    /**
     * Four-argument form for callers that do not care about the process budget:
     * the canonical constructor's default (the host's capacity) applies.
     */
    public MiniccProperties(String python, String repo, Duration budget, List<String> allowedRoots) {
        this(python, repo, budget, allowedRoots, null);
    }
}