"""M8-T123: a session path rule must only auto-consent paths inside its scope.

match_session_allowlist compared the *second* path form with
``rel.lstrip("./")``. ``str.lstrip`` erodes any leading character from the set
``{'.', '/'}`` — not a literal ``./`` prefix — so a relative path that escapes
with ``..`` (or an absolute path) had its prefix silently erased before matching.
A narrowly-scoped rule such as ``src/*.py`` therefore approved
``../src/evil.py``, ``../../src/evil.py`` and ``/src/a.py``: a trailing segment
that happens to line up is enough, even though the path leaves the directory the
user actually consented to. ``match_session_allowlist`` is the consent gate —
``audit.authorize_tool`` turns a True into "session_allowlist" with no interactive
prompt — so the over-match is a fail-open in user consent, not a cosmetic bug.

The ``./`` prefix was the only normalization the clause was for, so the fix is
``removeprefix("./")``: it keeps the intended tolerance and stops eating
escapes. These cases are deliberately paired so a wrong "fix" is caught:
``test_..._dot_slash_prefix`` stays green only if the second matcher still
normalizes ``./`` (it rejects deleting the clause outright), and the escape
cases stay green only if it stops normalizing ``..``.
"""

from __future__ import annotations

from pathlib import Path

from minicc.allowlist import add_session_rule, match_session_allowlist
from minicc.audit import authorize_tool


# A rule scoped to Python files under ``src/`` (relative to the workspace).
_PATTERN = "src/*.py"


def _rule(tmp_path: Path, session_id: str = "s1") -> None:
    add_session_rule(tmp_path, session_id, path=_PATTERN)


def test_paths_inside_the_rule_scope_are_auto_approved(tmp_path: Path) -> None:
    _rule(tmp_path)
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/main.py"})
    # The sole purpose of the second matcher: tolerate an explicit ./ prefix.
    # This is the control that rejects deleting the second matcher outright.
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "./src/main.py"})


def test_paths_outside_the_rule_scope_still_require_consent(tmp_path: Path) -> None:
    _rule(tmp_path)
    # The rule never covered non-.py siblings, and must not cover escaping or
    # absolute paths whose trailing segment merely coincides with the glob.
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/notes.txt"})
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "README.md"})


def test_dot_dot_escaping_path_is_not_auto_approved(tmp_path: Path) -> None:
    _rule(tmp_path)
    # ``src/*.py`` scoped to the workspace must NOT approve a path that walks up.
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "../src/evil.py"})
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "../../src/evil.py"})


def test_absolute_path_is_not_auto_approved_by_a_relative_rule(tmp_path: Path) -> None:
    _rule(tmp_path)
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "/src/a.py"})


def test_consent_seam_never_grants_an_escaping_path(tmp_path: Path) -> None:
    """Bind the invariant to the shipped dispatch path (audit.authorize_tool).

    authorize_tool downgrades a denial to ``authorization="session_allowlist"``
    exactly when the allowlist returns True. An escaping path must never reach
    that authorization; the in-scope ``./`` path must still reach it.
    """
    _rule(tmp_path)
    escaped = authorize_tool(
        "write_file",
        "write",
        {"path": "../src/evil.py"},
        allow_changes=False,
        allow_network=False,
        permission_mode="default",
        session_id="s1",
        workspace=tmp_path,
    )
    assert escaped.authorization != "session_allowlist", (
        "authorize_tool let a ../-escaping path be auto-approved by a "
        f"'{_PATTERN}' rule; authorization was {escaped.authorization!r}"
    )

    in_scope = authorize_tool(
        "write_file",
        "write",
        {"path": "./src/main.py"},
        allow_changes=False,
        allow_network=False,
        permission_mode="default",
        session_id="s1",
        workspace=tmp_path,
    )
    assert in_scope.allowed is True
    assert in_scope.authorization == "session_allowlist"
