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
 */
@ConfigurationProperties(prefix = "minicc")
public record MiniccProperties(String python, String repo, Duration budget, List<String> allowedRoots) {

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
    }
}