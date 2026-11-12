package com.minicc.cloud.bridge;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

/**
 * Reads the minicc change inspector over the process boundary.
 *
 * <p>Every failure mode leaves this class as a {@link BridgeUnavailableException}
 * carrying a reason. None of them returns an empty {@link ChangeSummary}: an
 * empty summary is a claim about the workspace ("nothing changed"), and a process
 * that could not be started, timed out, or printed something unparseable has not
 * earned the right to make that claim.
 */
public final class ChangeInspectorClient {

    private static final String SUMMARY_SCRIPT = String.join("\n",
            "import json, sys",
            "from minicc.changes import ChangeInspector",
            "print(json.dumps(ChangeInspector(sys.argv[1]).summary(), ensure_ascii=False))");

    private static final String DIFF_SCRIPT = String.join("\n",
            "import json, sys",
            "from minicc.changes import ChangeInspector",
            "print(json.dumps(ChangeInspector(sys.argv[1]).diff(sys.argv[2]), ensure_ascii=False))");

    private static final int SNIPPET = 2000;

    private final CommandRunner bridge;
    private final ObjectMapper mapper;

    public ChangeInspectorClient(CommandRunner bridge) {
        this.bridge = bridge;
        this.mapper = new ObjectMapper()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    }

    /** Convenience for a caller that owns the boundary directly: tests, CLIs. */
    public ChangeInspectorClient(Path python, Path repo, Duration budget) {
        this(new MiniccBridge(python, repo, budget));
    }

    /** The whole-workspace summary. Never empty on a failed read. */
    public ChangeSummary summary(Path workspace) {
        JsonNode node = read(SUMMARY_SCRIPT, List.of(workspace.toString()), "summary",
                List.of("files", "total_files"));
        try {
            return mapper.treeToValue(node, ChangeSummary.class);
        } catch (IOException exc) {
            throw new BridgeUnavailableException(
                    "the minicc summary could not be shaped into a ChangeSummary: " + exc, exc);
        }
    }

    /** One file's diff. {@code rawPath} is the spelling the trail recorded. */
    public ChangeRow diff(Path workspace, String rawPath) {
        JsonNode node = read(DIFF_SCRIPT, List.of(workspace.toString(), rawPath), "diff",
                List.of("path", "status"));
        try {
            return mapper.treeToValue(node, ChangeRow.class);
        } catch (IOException exc) {
            throw new BridgeUnavailableException(
                    "the minicc diff could not be shaped into a ChangeRow: " + exc, exc);
        }
    }

    private JsonNode read(String script, List<String> scriptArgs, String what,
                          List<String> requiredKeys) {
        List<String> args = new java.util.ArrayList<>(List.of("-c", script));
        args.addAll(scriptArgs);
        BridgeResponse response = bridge.run(args);
        if (!response.succeeded()) {
            throw new BridgeUnavailableException(
                    "the minicc " + what + " could not be read: " + response.failureReason());
        }
        String stdout = response.stdout();
        JsonNode node;
        try {
            node = mapper.readTree(stdout);
        } catch (IOException exc) {
            throw new BridgeUnavailableException(
                    "the minicc " + what + " exited 0 but did not print JSON: " + snippet(stdout), exc);
        }
        if (node == null || !node.isObject()) {
            throw new BridgeUnavailableException(
                    "the minicc " + what + " printed " + (node == null ? "nothing" : node.getNodeType())
                            + " where an object belongs: " + snippet(stdout));
        }
        for (String key : requiredKeys) {
            if (!node.has(key)) {
                // A missing key is not a zero. Saying so here keeps the caller
                // from reading a default and reporting a clean workspace.
                throw new BridgeUnavailableException(
                        "the minicc " + what + " left out '" + key + "': " + snippet(stdout));
            }
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