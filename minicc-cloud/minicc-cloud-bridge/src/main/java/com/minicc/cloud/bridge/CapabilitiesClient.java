package com.minicc.cloud.bridge;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

/**
 * Reads the tool catalogue the Python registry publishes.
 *
 * <p>This client exists so no Java code has to know a tool name or a count: the
 * answer is whatever {@code minicc --capabilities} printed. A process that
 * failed, timed out, or printed something that is not the promised object
 * leaves as a {@link BridgeUnavailableException} naming which of those happened;
 * it never becomes an empty catalogue, which a client would render as "minicc
 * ships no tools".
 */
public final class CapabilitiesClient {

    /**
     * The module entry, not an inline {@code -c} script: the flag under test is
     * the CLI's own, so a renamed or removed flag fails here instead of being
     * papered over by a snippet that rebuilds the payload in Java.
     */
    private static final List<String> CAPABILITIES_ARGS = List.of("-m", "minicc.main", "--capabilities");

    private static final int SNIPPET = 2000;

    private final CommandRunner bridge;
    private final ObjectMapper mapper = new ObjectMapper();

    public CapabilitiesClient(CommandRunner bridge) {
        this.bridge = bridge;
    }

    /** Convenience for a caller that owns the boundary directly: tests, CLIs. */
    public CapabilitiesClient(Path python, Path repo, Duration budget) {
        this(new MiniccBridge(python, repo, budget));
    }

    public JsonNode capabilities() {
        BridgeResponse response = bridge.run(CAPABILITIES_ARGS);
        if (!response.succeeded()) {
            throw new BridgeUnavailableException(
                    "the minicc capabilities could not be read: " + response.failureReason());
        }
        String stdout = response.stdout();
        JsonNode node;
        try {
            node = mapper.readTree(stdout);
        } catch (IOException exc) {
            throw new BridgeUnavailableException(
                    "the minicc capabilities exited 0 but did not print JSON: " + snippet(stdout), exc);
        }
        if (node == null || !node.isObject()) {
            throw new BridgeUnavailableException(
                    "the minicc capabilities printed "
                            + (node == null ? "nothing" : node.getNodeType())
                            + " where an object belongs: " + snippet(stdout));
        }
        if (!node.has("count") || !node.get("count").isInt()) {
            throw new BridgeUnavailableException(
                    "the minicc capabilities left out an integer 'count': " + snippet(stdout));
        }
        if (!node.has("tools") || !node.get("tools").isArray()) {
            throw new BridgeUnavailableException(
                    "the minicc capabilities left out a 'tools' array: " + snippet(stdout));
        }
        return node;
    }

    private static String snippet(String text) {
        if (text == null || text.isEmpty()) {
            return "(stdout was empty)";
        }
        String stripped = text.strip();
        return stripped.length() <= SNIPPET
                ? stripped
                : stripped.substring(0, SNIPPET) + "... (" + stripped.length() + " chars altogether)";
    }
}
