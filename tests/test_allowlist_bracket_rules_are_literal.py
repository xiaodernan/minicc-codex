"""M8-T124: allowlist path/tool rules treat literal brackets as literals.

Only the *commands* axis wraps its stored pattern with ``_escape_brackets``
(added in M2-T4 so a redacted ``[REDACTED:...]`` rule can match the redacted
runtime command). The ``tools`` and ``paths`` axes hand the stored pattern to
``fnmatch`` raw, so a rule the user typed with literal square brackets is read
as a fnmatch character class. That breaks the rule in BOTH directions:

- fail-open: ``releases[2.0]/*.jar`` also approves ``releases2/app.jar`` and
  ``releases./app.jar`` — a single substituted character where the class sat —
  files the user never consented to; ``match_session_allowlist`` is the consent
  gate (``audit.authorize_tool`` turns a True into "session_allowlist" with no
  prompt), so the over-match silently auto-approves out-of-scope paths.
- fail-closed: the literal path ``releases[2.0]/app.jar`` it was meant to cover
  is *not* approved, because the real ``[`` is not one of the class's characters.

Escaping brackets on these two axes fixes both while leaving ``*``/``?`` globbing
intact (that is exactly what ``_escape_brackets`` guarantees), which is why the
bracket-free-glob control must stay green in every variant.
"""

from __future__ import annotations

from pathlib import Path

from minicc.allowlist import add_session_rule, match_session_allowlist
from minicc.audit import authorize_tool


def test_path_bracket_rule_matches_its_literal_intended_path(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", path="releases[2.0]/*.jar")
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "releases[2.0]/app.jar"})
    # The *.jar wildcard must still match a different file name under the same dir.
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "releases[2.0]/lib.jar"})


def test_path_bracket_rule_does_not_char_class_match_variants(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", path="releases[2.0]/*.jar")
    # ``[2.0]`` as a character class would let a single substituted char match.
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "releases2/app.jar"})
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "releases./app.jar"})


def test_tool_bracket_rule_is_literal_not_char_class(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", tool="py[39]")
    assert match_session_allowlist(tmp_path, "s1", "py[39]", None)
    assert not match_session_allowlist(tmp_path, "s1", "py3", None)
    assert not match_session_allowlist(tmp_path, "s1", "py9", None)


def test_bracket_free_glob_still_works(tmp_path: Path) -> None:
    """Control: literalizing brackets must not disturb ordinary wildcard rules.

    This stays green on shipped code, on the fix, on every witness arm — it
    rejects any "fix" that over-escapes ``*``/``?`` and stops globbing.
    """
    add_session_rule(tmp_path, "s1", path="src/*.py")
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/main.py"})
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "docs/main.py"})


def test_consent_seam_literal_bracket_path(tmp_path: Path) -> None:
    """Bind the invariant to the shipped dispatch path (audit.authorize_tool)."""
    add_session_rule(tmp_path, "s1", path="releases[2.0]/*.jar")
    intended = authorize_tool(
        "write_file", "write", {"path": "releases[2.0]/app.jar"},
        allow_changes=False, allow_network=False, permission_mode="default",
        session_id="s1", workspace=tmp_path,
    )
    assert intended.allowed is True
    assert intended.authorization == "session_allowlist"

    substituted = authorize_tool(
        "write_file", "write", {"path": "releases2/app.jar"},
        allow_changes=False, allow_network=False, permission_mode="default",
        session_id="s1", workspace=tmp_path,
    )
    assert substituted.authorization != "session_allowlist", (
        "a [2.0] character-class rule auto-approved the substituted path "
        f"releases2/app.jar; authorization was {substituted.authorization!r}"
    )
