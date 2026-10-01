"""M8-T125: an allowlist path rule must not consent an embedded ``..`` escape.

``match_session_allowlist`` hands the candidate path to ``fnmatch``, which has no
path semantics: ``..`` segments are just characters, so a scope-escaping path keeps
the literal prefix the rule looks for. A rule scoped to ``src/`` therefore also
approves ``src/../../outside/x.py`` and ``src/../README.md`` — both of which resolve
OUT of ``src/``. A True here is the consent gate (``audit.authorize_tool`` turns it
into ``session_allowlist`` with no prompt), so out-of-scope targets are silently
auto-approved. This is the completeness gap of M8-T123: stripping a leading ``./``
does nothing about an *embedded* ``../``.

The fix collapses ``.``/``..`` on the candidate (posix normalisation, which is host
independent and matches the ``\\``->``/`` the code already applies) before matching,
so a normalised path must still literally sit under the rule's scope.
"""

from __future__ import annotations

from pathlib import Path

from minicc.allowlist import add_session_rule, match_session_allowlist
from minicc.audit import authorize_tool


def test_approves_in_scope_paths(tmp_path: Path) -> None:
    """In-scope approvals, including a deep path — must stay green (over-normalising
    a fix that kills legitimate ``src/`` coverage would redden this)."""
    add_session_rule(tmp_path, "s1", path="src/*")
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/main.py"})
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "./src/main.py"})
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/deep/nested/y.py"})


def test_denies_embedded_dotdot_escape(tmp_path: Path) -> None:
    """A ``..`` after the rule prefix escapes the scope and must NOT be consented."""
    add_session_rule(tmp_path, "s1", path="src/*")
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/../../outside/x.py"})
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/../README.md"})


def test_denies_leading_dotdot_and_absolute(tmp_path: Path) -> None:
    """Controls (M8-T123 invariants): leading ``../`` and absolute paths stay denied."""
    add_session_rule(tmp_path, "s1", path="src/*.py")
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "../src/evil.py"})
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "/src/a.py"})


def test_consent_seam_never_auto_approves_escaping(tmp_path: Path) -> None:
    """Bind the invariant to the shipped dispatch path (audit.authorize_tool)."""
    add_session_rule(tmp_path, "s1", path="src/*")
    in_scope = authorize_tool(
        "write_file", "write", {"path": "src/main.py"},
        allow_changes=False, allow_network=False, permission_mode="default",
        session_id="s1", workspace=tmp_path,
    )
    assert in_scope.allowed is True
    assert in_scope.authorization == "session_allowlist"

    escaping = authorize_tool(
        "write_file", "write", {"path": "src/../../outside/x.py"},
        allow_changes=False, allow_network=False, permission_mode="default",
        session_id="s1", workspace=tmp_path,
    )
    assert escaping.authorization != "session_allowlist", (
        f"a src/* rule auto-consented the scope-escaping path src/../../outside/x.py; "
        f"authorization was {escaping.authorization!r}"
    )
