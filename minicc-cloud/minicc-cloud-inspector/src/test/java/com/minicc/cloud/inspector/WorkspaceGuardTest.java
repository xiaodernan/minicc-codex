package com.minicc.cloud.inspector;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assumptions.abort;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/**
 * The workspace parameter is untrusted HTTP input handed to a child process.
 *
 * <p>Each refusal must carry the status that says which kind of refusal it was:
 * collapsing "outside the roots" into "does not exist" would let a caller probe
 * the host by reading the difference, and collapsing either into an empty
 * result would answer a question that was never allowed to be asked.
 */
class WorkspaceGuardTest {

    @TempDir Path temp;

    private WorkspaceGuard guard(List<String> roots) {
        return new WorkspaceGuard(
                new MiniccProperties("python", temp.toString(), Duration.ofSeconds(5), roots));
    }

    private static HttpStatus statusOf(Throwable thrown) {
        return (HttpStatus) ((ResponseStatusException) thrown).getStatusCode();
    }

    @Test
    void aBlankWorkspaceIsA400AndNotAReadOfTheCurrentDirectory() {
        WorkspaceGuard guard = guard(List.of());
        for (String blank : new String[] {null, "", "   "}) {
            assertThatThrownBy(() -> guard.resolve(blank))
                    .isInstanceOf(ResponseStatusException.class)
                    .matches(exc -> statusOf(exc) == HttpStatus.BAD_REQUEST);
        }
    }

    @Test
    void aWorkspaceThatDoesNotExistIsA404AndNotAnEmptyWorkspace() {
        Path absent = temp.resolve("never-created");
        assertThatThrownBy(() -> guard(List.of()).resolve(absent.toString()))
                .isInstanceOf(ResponseStatusException.class)
                .matches(exc -> statusOf(exc) == HttpStatus.NOT_FOUND);
    }

    @Test
    void aFileWhereADirectoryWasAskedForIsA400() throws IOException {
        Path file = Files.writeString(temp.resolve("notes.md"), "x");
        assertThatThrownBy(() -> guard(List.of()).resolve(file.toString()))
                .isInstanceOf(ResponseStatusException.class)
                .matches(exc -> statusOf(exc) == HttpStatus.BAD_REQUEST);
    }

    @Test
    void aDirectoryInsideTheRootIsAnsweredWithItsResolvedPath() throws IOException {
        Path inside = Files.createDirectory(temp.resolve("project"));
        assertThat(guard(List.of()).resolve(inside.toString())).isEqualTo(inside.toRealPath());
    }

    @Test
    void anEmptyAllowedRootsListMeansTheRepoAloneAndNotEverywhere() throws IOException {
        Path outside = Files.createDirectory(temp.resolveSibling("outside-" + temp.getFileName()));
        try {
            assertThatThrownBy(() -> guard(List.of()).resolve(outside.toString()))
                    .isInstanceOf(ResponseStatusException.class)
                    .matches(exc -> statusOf(exc) == HttpStatus.FORBIDDEN);
        } finally {
            Files.deleteIfExists(outside);
        }
    }

    /** {@code ..} is normalized away before the root comparison, not after it. */
    @Test
    void aTraversalThatLeavesTheRootIsRefusedEvenThoughItStartsInsideIt() throws IOException {
        Path inside = Files.createDirectory(temp.resolve("project"));
        Path sibling = Files.createDirectory(temp.resolve("sibling"));
        String escape = inside + "/../sibling";
        assertThatThrownBy(() -> guard(List.of(inside.toString())).resolve(escape))
                .isInstanceOf(ResponseStatusException.class)
                .matches(exc -> statusOf(exc) == HttpStatus.FORBIDDEN);
        assertThat(sibling).exists();
    }

    /**
     * A string-prefix comparison would authorise {@code ws-evil} because it
     * starts with the characters of {@code ws}. Path.startsWith is
     * component-wise; this pins that it stays that way.
     */
    @Test
    void aSiblingWhoseNameOnlySharesTheRootsPrefixIsNotInsideTheRoot() throws IOException {
        Path root = Files.createDirectory(temp.resolve("ws"));
        Path evil = Files.createDirectory(temp.resolve("ws-evil"));
        assertThatThrownBy(() -> guard(List.of(root.toString())).resolve(evil.toString()))
                .isInstanceOf(ResponseStatusException.class)
                .matches(exc -> statusOf(exc) == HttpStatus.FORBIDDEN);
    }

    @Test
    void aConfiguredRootThatDoesNotExistAuthorisesNothing() throws IOException {
        Path inside = Files.createDirectory(temp.resolve("project"));
        WorkspaceGuard guard = guard(List.of(temp.resolve("absent-root").toString()));
        assertThatThrownBy(() -> guard.resolve(inside.toString()))
                .isInstanceOf(ResponseStatusException.class)
                .matches(exc -> statusOf(exc) == HttpStatus.FORBIDDEN);
    }

    @Test
    void severalRootsAreEachHonoured() throws IOException {
        Path first = Files.createDirectory(temp.resolve("one"));
        Path second = Files.createDirectory(temp.resolve("two"));
        WorkspaceGuard guard = guard(List.of(first.toString(), second.toString()));
        assertThat(guard.resolve(second.toString())).isEqualTo(second.toRealPath());
        assertThat(guard.resolve(first.toString())).isEqualTo(first.toRealPath());
    }

    /**
     * The reason both sides go through toRealPath: a link that lives inside an
     * allowed root must not become a door to a directory outside it.
     */
    @Test
    void aSymlinkInsideTheRootPointingOutsideItIsRefused() throws IOException {
        Path root = Files.createDirectory(temp.resolve("root"));
        Path outside = Files.createDirectory(temp.resolve("outside"));
        Path link = root.resolve("escape");
        try {
            Files.createSymbolicLink(link, outside);
        } catch (IOException | UnsupportedOperationException exc) {
            abort("symlinks unavailable on this platform: " + exc.getMessage());
        }
        assertThatThrownBy(() -> guard(List.of(root.toString())).resolve(link.toString()))
                .isInstanceOf(ResponseStatusException.class)
                .matches(exc -> statusOf(exc) == HttpStatus.FORBIDDEN);
    }

    /** A refused workspace must not be reported as a workspace that is clean. */
    @Test
    void everyRefusalCarriesAReasonThatNamesWhatWasRefused() throws IOException {
        Path outside = Files.createDirectory(temp.resolve("elsewhere"));
        WorkspaceGuard guard = guard(List.of(temp.resolve("root").toString()));
        assertThatThrownBy(() -> guard.resolve(outside.toString()))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("outside the configured roots")
                .hasMessageContaining(outside.toRealPath().toString());
    }
}