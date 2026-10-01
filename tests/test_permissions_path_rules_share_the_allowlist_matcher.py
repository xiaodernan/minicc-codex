"""M8-T126: permissions.json must mean the same thing as the session allowlist.

``minicc/permissions.py`` carried a hand-copied clone of the three fnmatch axes
from ``match_session_allowlist``. M8-T123 (``rel.lstrip("./")`` erodes any leading
character from the set ``{'.', '/'}``, so it eats ``..`` and ``/``), M8-T124 (a raw
``[`` is read as a character class) and M8-T125 (fnmatch has no path semantics, so
an embedded ``../`` keeps the literal prefix the rule looks for) were each fixed in
the first copy and never in the second.

Both files are consent gates: ``web.should_allow`` skips the interactive prompt when
``match_permission_rule`` returns ``"allow"``, exactly as ``audit.authorize_tool``
does for a True from the session allowlist. So a rule written into a checked-in
``permissions.json`` auto-consented paths its allowlist twin had already learned to
refuse — a fail-open in user consent, reachable from the shipped dispatch path.

The defect is the duplication rather than the three lines, so a fix that re-pasted
the correct predicate would simply be red again the next time one file was edited.
The matchers are now shared, and the last test feeds one battery of paths through
*both* gates and requires the same verdict: that is the fence which notices a
re-copy.

One asymmetry is recorded here instead of smoothed over. The shared normalisation
also narrows the ``deny`` side for paths that walk out of the workspace
(``../secrets/k.txt`` no longer matches a ``secrets/*`` rule). That opens nothing:
the editor the path tools go through refuses an escaping path before any rule is
consulted, which ``test_escaping_paths_are_refused_at_the_filesystem_layer``
measures rather than asserts in prose. The narrowing that matters runs the other
way — a path that *denotes* an inside target (``docs/../secrets/k.txt``) is now
denied, where the old raw comparison saw a ``docs/`` prefix and let the veto slip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.allowlist import add_session_rule, match_session_allowlist
from minicc.permissions import _cache as permissions_cache
from minicc.permissions import match_permission_rule
from minicc.tools.editor import Editor, EditError

#: A rule scoped to Python files directly under ``src/`` (workspace-relative).
_ALLOW_RULE = "src/*.py"


def _permissions(
    workspace: Path,
    *,
    allow_paths: tuple[str, ...] = (),
    deny_paths: tuple[str, ...] = (),
    allow_tools: tuple[str, ...] = (),
) -> Path:
    """Write a checked-in ``permissions.json`` and drop the rules cache.

    The cache is keyed on ``(mtime_ns, size)``, so a fixture that reuses a
    directory would otherwise be judged by the previous test's rules.
    """
    directory = workspace / ".minicc"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "permissions.json").write_text(
        json.dumps(
            {
                "allow": {"tools": list(allow_tools), "commands": [], "paths": list(allow_paths)},
                "deny": {"tools": [], "commands": [], "paths": list(deny_paths)},
            }
        ),
        encoding="utf-8",
    )
    permissions_cache.clear()
    return workspace


def test_an_allow_path_rule_does_not_consent_an_escaping_path(tmp_path: Path) -> None:
    """The shipped fail-open, read at the consent gate itself."""
    _permissions(tmp_path, allow_paths=(_ALLOW_RULE,))
    for escaping in (
        "../src/evil.py",
        "/src/a.py",
        "src/../../outside/x.py",
        "src/../README.md",
    ):
        assert match_permission_rule(tmp_path, "write_file", {"path": escaping}) is None, (
            f"a permissions.json rule of {_ALLOW_RULE!r} auto-consented {escaping!r}, "
            "which walks outside the directory the rule names"
        )


def test_the_ordinary_in_scope_case_still_skips_the_prompt(tmp_path: Path) -> None:
    """Control against a fix that narrows past the shipped semantics."""
    _permissions(tmp_path, allow_paths=(_ALLOW_RULE,))
    assert match_permission_rule(tmp_path, "write_file", {"path": "src/main.py"}) == "allow"
    # Tolerating an explicit ./ prefix was the only thing lstrip("./") was for;
    # normpath("./src/main.py") == "src/main.py" keeps that promise.
    assert match_permission_rule(tmp_path, "write_file", {"path": "./src/main.py"}) == "allow"
    assert match_permission_rule(tmp_path, "write_file", {"path": "docs/a.py"}) is None


def test_a_literal_bracket_in_a_tool_rule_stays_a_literal(tmp_path: Path) -> None:
    """M8-T124's tools axis, missing from the second copy.

    ``re[a-d]d_file`` spells ``read_file`` as soon as fnmatch reads the brackets as
    a character class, so the old raw match let a rule that named a *different*
    tool approve ``read_file`` with no prompt.
    """
    _permissions(tmp_path, allow_tools=("re[a-d]d_file",))
    assert match_permission_rule(tmp_path, "read_file", {}) is None
    _permissions(tmp_path, allow_tools=("read_file",))
    assert match_permission_rule(tmp_path, "read_file", {}) == "allow"


def test_a_path_that_denotes_an_inside_target_is_denied_by_an_inside_rule(tmp_path: Path) -> None:
    """Normalisation tightens ``deny`` for the direction that matters.

    ``docs/../secrets/k.txt`` *is* ``secrets/k.txt``; the old raw comparison looked
    at a ``docs/`` prefix and let a ``secrets/*`` veto slip past it.
    """
    _permissions(tmp_path, deny_paths=("secrets/*.txt",))
    assert match_permission_rule(tmp_path, "read_file", {"path": "docs/../secrets/k.txt"}) == "deny"
    assert match_permission_rule(tmp_path, "read_file", {"path": "secrets/k.txt"}) == "deny"
    assert match_permission_rule(tmp_path, "read_file", {"path": "notes.txt"}) is None


def test_escaping_paths_are_refused_at_the_filesystem_layer(tmp_path: Path) -> None:
    """Why the recorded ``deny`` narrowing opens nothing.

    Measured at the editor every path tool goes through, not claimed in a comment:
    a workspace-escaping or absolute path is refused there, so no rule verdict is
    ever consulted for it.
    """
    (tmp_path / "inside.txt").write_text("keep", encoding="utf-8")
    editor = Editor(tmp_path)
    with pytest.raises(EditError):
        editor.write_file("../t126-never-write.txt", "boom")
    with pytest.raises(EditError):
        editor.write_file("/absolute/t126-never-write.txt", "boom")
    assert not (tmp_path.parent / "t126-never-write.txt").exists()
    assert not Path("/absolute/t126-never-write.txt").exists()
    assert (tmp_path / "inside.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "path",
    [
        "src/main.py",
        "./src/main.py",
        "src/deep/nested/y.py",
        "src/notes.txt",
        "../src/evil.py",
        "/src/a.py",
        "src/../../outside/x.py",
        "docs/../src/main.py",
        "src/../README.md",
        "README.md",
    ],
)
def test_the_two_consent_gates_agree_on_every_path_shape(
    tmp_path: Path, path: str
) -> None:
    """The root-cause fence: one matcher, two rule files.

    If either gate grows its own copy of the comparison again, this goes red on the
    first path shape the copies disagree about — which is exactly how M8-T123,
    M8-T124 and M8-T125 came to be fixed in one file and missed in the other.
    """
    _permissions(tmp_path, allow_paths=(_ALLOW_RULE,))
    add_session_rule(tmp_path, "s1", path=_ALLOW_RULE)
    permitted = match_permission_rule(tmp_path, "write_file", {"path": path}) == "allow"
    consented = match_session_allowlist(tmp_path, "s1", "write_file", {"path": path})
    assert permitted is consented, (
        f"permissions.json and allowlist.json disagree about {path!r} "
        f"under the same {_ALLOW_RULE!r} rule: "
        f"permissions={permitted}, allowlist={consented}"
    )
