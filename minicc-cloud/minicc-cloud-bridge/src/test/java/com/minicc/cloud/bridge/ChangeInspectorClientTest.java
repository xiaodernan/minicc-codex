package com.minicc.cloud.bridge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * The bridge is tested against a real Python child, not a mock, because every
 * defect it exists to prevent lives in the process boundary: a full pipe, a
 * non-UTF-8 code page, a child that never exits, a stdout that is not JSON.
 *
 * <p>The stub {@code minicc.changes} module below stands in for the repo's own
 * inspector so the tests do not need a git workspace. It prints whatever the
 * test put in {@code payload.json}, which keeps the payload under test control.
 */
class ChangeInspectorClientTest {

    private static final String PYTHON = System.getProperty("minicc.python", "python");
    private static final Duration BUDGET = Duration.ofSeconds(20);

    private static final String STUB = String.join("\n",
            "import json, sys, time",
            "from pathlib import Path",
            "MODE = Path('mode.txt').read_text(encoding='utf-8').strip() if Path('mode.txt').exists() else 'ok'",
            "class ChangeInspector:",
            "    def __init__(self, workspace):",
            "        self.workspace = workspace",
            "    def _payload(self, name):",
            "        return Path(name).read_text(encoding='utf-8')",
            "    def summary(self):",
            "        if MODE == 'exit':",
            "            sys.stderr.write('the trail could not be opened')",
            "            sys.exit(3)",
            "        if MODE == 'garbage':",
            "            print('this is not json')",
            "            return {}",
            "        if MODE == 'silent':",
            "            sys.exit(0)",
            "        if MODE == 'sleep':",
            "            time.sleep(60)",
            "            return {}",
            "        if MODE == 'flood':",
            "            sys.stderr.write('e' * 1048576)",
            "            sys.stderr.flush()",
            "        return json.loads(self._payload('payload.json'))",
            "    def diff(self, raw_path):",
            "        return json.loads(self._payload('diff.json'))",
            "");

    @TempDir
    Path repo;

    private Path workspace;

    @BeforeEach
    void layOutTheStubRepo() throws IOException {
        Path pkg = repo.resolve("minicc");
        Files.createDirectories(pkg);
        Files.writeString(pkg.resolve("__init__.py"), "", StandardCharsets.UTF_8);
        Files.writeString(pkg.resolve("changes.py"), STUB, StandardCharsets.UTF_8);
        workspace = repo.resolve("ws");
        Files.createDirectories(workspace);
        write("payload.json", """
                {"files": [{"path": "notes.md", "status": "modified", "additions": 3,
                            "deletions": 1, "patch": "-old\\n+new"}],
                 "total_files": 1, "additions": 3, "deletions": 1,
                 "files_without_counts": 0, "truncated": false, "shown_files": 1,
                 "audit_window_truncated": false, "audit_bytes_unread": 0,
                 "audit_records_split": 0, "status_read_error": null,
                 "audit_read_error": null, "audit_unreadable_lines": 0}
                """);
        write("diff.json", """
                {"path": "notes.md", "status": "modified", "additions": 3, "deletions": 1,
                 "patch": "-old\\n+new", "deletion_preimage": "", "audit_window_truncated": false}
                """);
    }

    private void write(String name, String text) throws IOException {
        Files.writeString(repo.resolve(name), text, StandardCharsets.UTF_8);
    }

    private void mode(String value) throws IOException {
        write("mode.txt", value);
    }

    private ChangeInspectorClient client() {
        return client(BUDGET);
    }

    private ChangeInspectorClient client(Duration budget) {
        return new ChangeInspectorClient(Path.of(PYTHON), repo, budget);
    }

    // ----------------------------------------------------------------------
    // The happy path, and the control that proves the stub really ran
    // ----------------------------------------------------------------------

    @Test
    void theSummaryArrivesWithItsNumbersIntact() {
        ChangeSummary summary = client().summary(workspace);

        assertThat(summary.totalFiles()).isEqualTo(1);
        assertThat(summary.additions()).isEqualTo(3);
        assertThat(summary.deletions()).isEqualTo(1);
        assertThat(summary.partial()).isFalse();
        assertThat(summary.files()).hasSize(1);
        assertThat(summary.files().get(0).path()).isEqualTo("notes.md");
        assertThat(summary.files().get(0).uncounted()).isFalse();
    }

    @Test
    void theStubReallyReadsThePayloadTheTestWrote() throws IOException {
        // Anti-vacuity: if the client returned a constant, changing the payload
        // would not change the answer and every gate below would be decorative.
        write("payload.json", """
                {"files": [], "total_files": 42, "additions": 0, "deletions": 0,
                 "files_without_counts": 0, "truncated": false, "shown_files": 0,
                 "audit_window_truncated": false, "audit_bytes_unread": 0,
                 "audit_records_split": 0, "status_read_error": null,
                 "audit_read_error": null, "audit_unreadable_lines": 0}
                """);

        assertThat(client().summary(workspace).totalFiles()).isEqualTo(42);
    }

    @Test
    void oneFilesDiffArrivesAsARow() {
        ChangeRow row = client().diff(workspace, "notes.md");

        assertThat(row.path()).isEqualTo("notes.md");
        assertThat(row.status()).isEqualTo("modified");
        assertThat(row.additions()).isEqualTo(3);
        assertThat(row.patch()).contains("-old");
    }

    // ----------------------------------------------------------------------
    // Unknown is not zero
    // ----------------------------------------------------------------------

    @Test
    void aNullCountStayNullInsteadOfBecomingZero() throws IOException {
        write("payload.json", """
                {"files": [{"path": "notes.md", "status": "modified",
                            "additions": null, "deletions": null}],
                 "total_files": 1, "additions": null, "deletions": null,
                 "files_without_counts": 1, "truncated": false, "shown_files": 1,
                 "audit_window_truncated": false, "audit_bytes_unread": 0,
                 "audit_records_split": 0, "status_read_error": null,
                 "audit_read_error": null, "audit_unreadable_lines": 0}
                """);

        ChangeSummary summary = client().summary(workspace);

        assertThat(summary.additions()).isNull();
        assertThat(summary.deletions()).isNull();
        assertThat(summary.files().get(0).additions()).isNull();
        assertThat(summary.files().get(0).uncounted()).isTrue();
        assertThat(summary.partial()).isTrue();
    }

    @Test
    void aFailedStatusReadIsPartialEvenWhenTheTotalSaysZero() throws IOException {
        write("payload.json", """
                {"files": [], "total_files": 0, "additions": 0, "deletions": 0,
                 "files_without_counts": 0, "truncated": false, "shown_files": 0,
                 "audit_window_truncated": false, "audit_bytes_unread": null,
                 "audit_records_split": null, "status_read_error": "git status exited 128",
                 "audit_read_error": null, "audit_unreadable_lines": 0}
                """);

        ChangeSummary summary = client().summary(workspace);

        assertThat(summary.totalFiles()).isZero();
        assertThat(summary.statusReadError()).isEqualTo("git status exited 128");
        assertThat(summary.auditBytesUnread()).isNull();
        assertThat(summary.partial()).isTrue();
    }

    @Test
    void aCutAuditWindowMakesTheAnswerPartial() throws IOException {
        write("payload.json", """
                {"files": [], "total_files": 0, "additions": 0, "deletions": 0,
                 "files_without_counts": 0, "truncated": false, "shown_files": 0,
                 "audit_window_truncated": true, "audit_bytes_unread": 4096,
                 "audit_records_split": 1, "status_read_error": null,
                 "audit_read_error": null, "audit_unreadable_lines": 0}
                """);

        ChangeSummary summary = client().summary(workspace);

        assertThat(summary.auditWindowTruncated()).isTrue();
        assertThat(summary.auditBytesUnread()).isEqualTo(4096);
        assertThat(summary.auditRecordsSplit()).isEqualTo(1);
        assertThat(summary.partial()).isTrue();
    }

    // ----------------------------------------------------------------------
    // A failed read is never an empty summary
    // ----------------------------------------------------------------------

    @Test
    void aNonZeroExitCarriesTheReasonAndDoesNotReturnASummary() throws IOException {
        mode("exit");

        assertThatThrownBy(() -> client().summary(workspace))
                .isInstanceOf(BridgeUnavailableException.class)
                .hasMessageContaining("exited 3")
                .hasMessageContaining("the trail could not be opened");
    }

    @Test
    void stdoutThatIsNotJsonCarriesTheTextItPrinted() throws IOException {
        mode("garbage");

        assertThatThrownBy(() -> client().summary(workspace))
                .isInstanceOf(BridgeUnavailableException.class)
                .hasMessageContaining("did not print JSON")
                .hasMessageContaining("this is not json");
    }

    @Test
    void anEmptyStdoutWithExitZeroIsStillAFailure() throws IOException {
        mode("silent");

        assertThatThrownBy(() -> client().summary(workspace))
                .isInstanceOf(BridgeUnavailableException.class)
                .hasMessageContaining("stdout was empty");
    }

    @Test
    void aMissingTotalFilesIsNamedNotDefaultedToZero() throws IOException {
        write("payload.json", """
                {"files": [], "additions": 0, "deletions": 0}
                """);

        assertThatThrownBy(() -> client().summary(workspace))
                .isInstanceOf(BridgeUnavailableException.class)
                .hasMessageContaining("left out 'total_files'");
    }

    @Test
    void aMissingInterpreterIsATransportErrorNotACleanWorkspace() {
        ChangeInspectorClient broken = new ChangeInspectorClient(
                repo.resolve("no-such-python"), repo, BUDGET);

        assertThatThrownBy(() -> broken.summary(workspace))
                .isInstanceOf(BridgeUnavailableException.class)
                .hasMessageContaining("could not start");
    }

    @Test
    void aChildThatNeverFinishesIsReportedAsATimeout() throws IOException {
        mode("sleep");

        assertThatThrownBy(() -> client(Duration.ofMillis(600)).summary(workspace))
                .isInstanceOf(BridgeUnavailableException.class)
                .hasMessageContaining("did not finish within");
    }

    // ----------------------------------------------------------------------
    // The pipe itself
    // ----------------------------------------------------------------------

    @Test
    void aMegabyteOnStderrDoesNotDeadlockTheStdoutRead() throws IOException {
        mode("flood");

        ChangeSummary summary = client().summary(workspace);

        assertThat(summary.totalFiles()).isEqualTo(1);
    }

    @Test
    void aCjkPathCrossesThePipeWithoutBecomingReplacementCharacters() throws IOException {
        write("payload.json", """
                {"files": [{"path": "面试项目/notes.md",
                            "status": "modified", "additions": 1, "deletions": 0}],
                 "total_files": 1, "additions": 1, "deletions": 0,
                 "files_without_counts": 0, "truncated": false, "shown_files": 1,
                 "audit_window_truncated": false, "audit_bytes_unread": 0,
                 "audit_records_split": 0, "status_read_error": null,
                 "audit_read_error": null, "audit_unreadable_lines": 0}
                """);

        ChangeSummary summary = client().summary(workspace);

        assertThat(summary.files().get(0).path()).isEqualTo("面试项目/notes.md");
        assertThat(summary.files().get(0).path()).doesNotContain("\uFFFD");
    }

    @Test
    void theStderrFloodIsDrainedWholeNotTruncatedAtThePipeBuffer() throws IOException {
        mode("flood");
        MiniccBridge bridge = new MiniccBridge(Path.of(PYTHON), repo, BUDGET);

        BridgeResponse response = bridge.run(java.util.List.of("-c",
                "import sys; sys.stderr.write('e' * 1048576); sys.stderr.flush(); print('{}')"));

        assertThat(response.succeeded()).isTrue();
        assertThat(response.stderr()).hasSize(1048576);
    }

    // ----------------------------------------------------------------------
    // BridgeResponse keeps the three failures apart
    // ----------------------------------------------------------------------

    @Test
    void theThreeFailureShapesEachNameThemselves() {
        BridgeResponse ok = new BridgeResponse(0, "{}", "", false, null, Duration.ofMillis(5));
        BridgeResponse exited = new BridgeResponse(3, "", "boom", false, null, Duration.ofMillis(5));
        BridgeResponse timedOut = new BridgeResponse(-1, "", "", true, null, Duration.ofSeconds(20));
        BridgeResponse transport = new BridgeResponse(-1, "", "", false,
                "could not read the child's stdout whole: closed", Duration.ofMillis(5));
        BridgeResponse quiet = new BridgeResponse(1, "", "", false, null, Duration.ofMillis(5));

        assertThat(ok.succeeded()).isTrue();
        assertThat(ok.failureReason()).isNull();
        assertThat(exited.failureReason()).contains("exited 3").contains("boom");
        assertThat(timedOut.failureReason()).contains("did not finish within");
        assertThat(transport.failureReason()).contains("stdout whole");
        assertThat(quiet.failureReason()).contains("wrote nothing to stderr");
        for (BridgeResponse failure : java.util.List.of(exited, timedOut, transport, quiet)) {
            assertThat(failure.succeeded()).isFalse();
            assertThat(failure.failureReason()).isNotNull().isNotBlank();
        }
    }
}