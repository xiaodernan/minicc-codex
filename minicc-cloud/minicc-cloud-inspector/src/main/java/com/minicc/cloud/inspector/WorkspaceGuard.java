package com.minicc.cloud.inspector;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/**
 * Decides which directories an HTTP caller is allowed to name.
 *
 * <p>The workspace arrives as a request parameter and is handed to a child
 * process, so it is untrusted input at a system boundary. Both sides are
 * resolved through {@code toRealPath} before comparison: a symlink inside an
 * allowed root must not become a way to read a directory outside it.
 */
@Component
public class WorkspaceGuard {

    private final List<Path> roots;

    public WorkspaceGuard(MiniccProperties properties) {
        Path repo = Path.of(properties.repo()).toAbsolutePath().normalize();
        List<String> configured = properties.allowedRoots().isEmpty()
                ? List.of(repo.toString())
                : properties.allowedRoots();
        this.roots = configured.stream().map(WorkspaceGuard::real).toList();
    }

    private static Path real(String value) {
        Path path = Path.of(value).toAbsolutePath().normalize();
        try {
            return path.toRealPath();
        } catch (IOException exc) {
            // A root that does not exist yet cannot authorise anything; keeping
            // the normalized form means startsWith simply never matches it.
            return path;
        }
    }

    /** The resolved workspace, or a status that says why it was refused. */
    public Path resolve(String requested) {
        if (requested == null || requested.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "workspace must name a directory");
        }
        Path candidate = Path.of(requested).toAbsolutePath().normalize();
        Path resolved;
        try {
            resolved = candidate.toRealPath();
        } catch (IOException exc) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "workspace does not exist or cannot be reached: " + candidate);
        }
        if (!Files.isDirectory(resolved)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "workspace is not a directory: " + resolved);
        }
        for (Path root : roots) {
            if (resolved.startsWith(root)) {
                return resolved;
            }
        }
        throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                "workspace is outside the configured roots: " + resolved);
    }
}