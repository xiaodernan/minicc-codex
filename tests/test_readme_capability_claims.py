"""The README's capability list names env vars, flags, endpoints and workspace files.

Those names are how a reader decides whether this project does what they need, and they
are also the part that rots silently: rename a variable, drop a flag, move an endpoint, and
the list goes on claiming it. Nothing checked the list before this file - the config surface
gates check that a *new* key is documented in ``minicc.config.example``, which is the other
direction, and they do not read the README at all.

What this checks is existence, not behaviour: a name that is present but wired to nothing
would pass here. That limit is deliberate - the behaviour of each claim belongs to the gate
for that feature (the sandbox fallback refusal to ``test_core_tools``, the non-loopback
auth requirement to ``test_web_security``, the private-fetch refusal to ``test_webfetch``),
and this file's job is the much smaller one of noticing when the name itself is gone.

Floors are asserted so that a README that loses its capability section, or an extractor
that stops matching, cannot pass by finding nothing.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
README = REPO / "README.md"

#: Anti-vacuity floors. The capability list carried 13 env vars, 7 flags in that section,
#: 6 endpoints and 3 workspace files when this gate was written; the floors sit below that
#: so ordinary edits pass and an empty or unparsed section cannot. Flags are now extracted
#: from the whole README (the capability list plus the install/run examples), which names
#: 19 distinct flags - the floor sits well below that.
MIN_ENV_NAMES = 10
MIN_FLAGS = 12
MIN_ENDPOINTS = 4
MIN_WORKSPACE_FILES = 2


def _capability_section() -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index("## 当前能力")
    end = text.find("\n## ", start + 5)
    return text[start:] if end == -1 else text[start:end]


def _whole_readme() -> str:
    """Endpoints and CLI flags are named where they are used, not only in the capability list.

    The list names one endpoint (the history search); ``/api/metrics``, ``/api/audit`` and
    the task routes are documented in the sections that explain them, so the endpoint check
    reads the whole file. The same is true of CLI flags: the capability list names a few
    (``--permission-mode``, ``--yolo``, ``--verbose-tools`` ...), but the install/run
    examples name more (``--host``, ``--port``, ``--version``, ``--session-id``,
    ``--resume``), so the flag check reads the whole file too. Environment variables and
    workspace files stay scoped to the capability list - they are that section's vocabulary.
    """
    return README.read_text(encoding="utf-8")


def _sources() -> str:
    """Every Python file that could name one of these, concatenated."""
    parts: list[str] = []
    for path in sorted(REPO.glob("minicc/**/*.py")) + sorted(REPO.glob("scripts/*.py")):
        if "__pycache__" in path.parts:
            continue
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _mentions(source: str, name: str) -> bool:
    """Is ``name`` present as a whole token, not as a prefix of something longer?

    The first version of this gate used ``name in source``, and its own mutation arm showed
    why that is not enough: renaming ``MINICC_WORKSPACE_ROOTS`` to
    ``MINICC_WORKSPACE_ROOTS_RENAMED`` left the gate green, because the old name is a
    substring of the new one. Word boundaries make a rename a rename.
    """
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", source) is not None


def _readme_flag_tokens(text: str) -> list[str]:
    """Every ``--flag`` that appears inside a code region of the README.

    The capability list writes flags as inline `` `--flag` `` spans, but the install/run
    examples put them in fenced ``` blocks - a single-backtick regex misses those. This
    pools both inline spans and fenced blocks so a flag documented only in a run example is
    still checked against the parser.
    """
    inline = re.findall(r"`([^`]+)`", text)
    fenced = re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", text, re.S)
    pool = "\n".join(inline + fenced)
    return sorted(set(re.findall(r"--[a-z][a-z0-9-]+", pool)))


def test_the_extraction_finds_a_list_of_real_size() -> None:
    section = _capability_section()
    assert len(re.findall(r"`MINICC_[A-Z0-9_]+", section)) >= MIN_ENV_NAMES, section[:400]
    # Flags are extracted from the whole README (inline spans + fenced run examples).
    assert len(_readme_flag_tokens(_whole_readme())) >= MIN_FLAGS, section[:400]
    assert len(re.findall(r"/api/[A-Za-z0-9_/.-]+", _whole_readme())) >= MIN_ENDPOINTS, section[:400]


def test_every_environment_variable_the_list_names_is_read_somewhere() -> None:
    section = _capability_section()
    names = sorted(set(re.findall(r"`(MINICC_[A-Z0-9_]+)", section)))
    assert len(names) >= MIN_ENV_NAMES, names
    source = _sources()
    missing = [name for name in names if not _mentions(source, name)]
    assert not missing, (
        "the capability list names environment variables no source reads: "
        f"{missing} - either the variable was renamed or the claim is stale"
    )


def _check_flags(text: str) -> None:
    flags = _readme_flag_tokens(text)
    assert len(flags) >= MIN_FLAGS, flags
    source = _sources()
    missing = [flag for flag in flags if not _mentions(source, flag)]
    assert not missing, f"the README names flags no parser declares: {missing}"


def test_every_flag_the_readme_names_exists_in_a_parser() -> None:
    # Flags are extracted from the whole README (inline spans + fenced run examples): the
    # capability list plus the install/run examples. An install/run example that names a flag
    # the parser does not declare (or a flag that was renamed away) turns this red - which is
    # the point.
    _check_flags(_whole_readme())


def test_the_flag_gate_catches_a_renamed_fenced_flag() -> None:
    # Mutation arm for the widened (fenced-block-aware) extraction: rename ``--host`` - an
    # install/run example flag that lives inside a fenced ``` block, not an inline span - and
    # the gate must go red. ``_mentions`` word-boundary matching is already proven by the
    # batch 225 env-var arm; this arm proves the fenced-block path is actually checked.
    original = "--host"
    renamed = "--renamed-host"
    readme = _whole_readme()
    assert original in readme, "anchor: original flag must be present"
    tampered = readme.replace(original, renamed)
    assert original not in tampered and renamed in tampered, (
        "anchor: the rename must have actually been applied and must not keep the old name as a prefix"
    )
    with pytest.raises(AssertionError):
        _check_flags(tampered)


def test_every_endpoint_the_readme_names_is_routed() -> None:
    endpoints = sorted(set(re.findall(r"(/api/[A-Za-z0-9_/.-]+)", _whole_readme())))
    assert len(endpoints) >= MIN_ENDPOINTS, endpoints
    source = _sources()
    missing = [endpoint for endpoint in endpoints if f'"{endpoint}' not in source]
    # `/api/nope` is the README's deliberate example of an unknown route.
    missing = [endpoint for endpoint in missing if endpoint != "/api/nope"]
    assert not missing, f"the README names endpoints nothing routes: {missing}"


@pytest.mark.parametrize(
    "workspace_file",
    sorted(set(re.findall(r"`(\.minicc/[a-z_]+\.json)`", _capability_section()))),
)
def test_every_workspace_file_the_list_names_is_used(workspace_file: str) -> None:
    assert _mentions(_sources(), workspace_file), (
        f"the capability list names {workspace_file}, which no source mentions"
    )
