"""M8-T711 — a line a test docstring cites is a line a reader can still read.

Test docstrings point at the tree in the same ``path:line`` form the shipped
documents use (``tests/test_bench_tasks.py:339``).  The
document reader (``scripts/doc_pointers.py``) walks ``docs/`` and README only,
so nothing ever read the test side: measured 2026-11-09 on this tree, 96
citations across 577 tracked test modules.

This gate does not claim a line still says what the sentence says — that needs
the quoted token, and most sentences quote a concept rather than a literal.
It pins what can be pinned without a hand-written roster for all 96: the path
resolves, the line is in range, and the line has something on it.  Ten
citations — the ones this batch re-aimed — are pinned harder, by a token
their target line must still contain, so the next move has to come back here.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"

#: The citation form: a path with a code suffix, a colon, and the first line
#: of the cited run.  ``minicc/web.py:1804``/``:2310`` (a bare ``:NNN`` tail)
#: is not a second citation -- it inherits the path.
CITATION = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|md|mjs|js|ts|tsx|json|ya?ml))[:：](\d+)")

#: (path, line, token) for the citations this batch re-aimed.  Each token is
#: the thing the sentence says is there; all are matched case-sensitively.
REPAIRED = (
    ("minicc/mcp.py", 52, "class McpError"),
    ("minicc/mcp.py", 69, "Fold every character"),
    ("minicc/mcp.py", 730, "Mcp-Session-Id"),
    ("minicc/agent/verifier.py", 62, "def passed"),
    ("minicc/agent/completion.py", 23, "classify_provider_failure"),
    ("minicc/agent/completion.py", 342, "text = re.sub"),
    ("minicc/agent/completion.py", 394, "完成评估与最新客观验证结果冲突"),
    ("minicc/task_manager.py", 995, "dict(self.result)"),
    ("minicc/web.py", 1804, "record_text(8000)"),
    ("tests/test_mcp_http.py", 134, "load_mcp_config(tmp_path)"),
)


def _tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stderr[-2000:]
    return set(out.stdout.splitlines())


def _index(tracked: set[str]) -> dict[str, list[str]]:
    by_base: dict[str, list[str]] = {}
    for path in tracked:
        by_base.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    return by_base


def resolve(token: str, tracked: set[str], index: dict[str, list[str]]) -> str | None:
    """The tracked path a docstring token means, or ``None``.

    A bare ``mcp.py`` is how these sentences name ``minicc/mcp.py``; it is
    accepted only when the basename is unique in the tree, so an ambiguous
    token fails here instead of picking one silently.
    """
    for prefix in ("", "minicc/", "tests/", "scripts/", "docs/"):
        candidate = prefix + token
        if candidate in tracked:
            return candidate
    hits = index.get(token.rsplit("/", 1)[-1], [])
    return hits[0] if len(hits) == 1 else None


def docstrings(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    found = [("<module>", ast.get_docstring(tree) or "")]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            found.append((f"class {node.name}", ast.get_docstring(node) or ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((f"def {node.name}", ast.get_docstring(node) or ""))
    return found


def _offenders(text: str, where: str, resolve_one) -> list[str]:
    bad: list[str] = []
    for match in CITATION.finditer(text):
        token, line = match.group(1), int(match.group(2))
        target = resolve_one(token)
        if target is None:
            bad.append(f"{where}: {token}:{line} does not resolve to a tracked path")
            continue
        body = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if not 0 < line <= len(body):
            bad.append(f"{where}: {token}:{line} is outside {target} ({len(body)} lines)")
        elif not body[line - 1].strip():
            bad.append(f"{where}: {token}:{line} lands on a blank line in {target}")
    return bad


def _repo_resolver(tracked: set[str], index: dict[str, list[str]]):
    return lambda token: (REPO / path) if (path := resolve(token, tracked, index)) else None


def _corpus_citations() -> list[tuple[str, str, str, int]]:
    tracked = _tracked()
    index = _index(tracked)
    rows: list[tuple[str, str, str, int]] = []
    for path in sorted(TESTS.glob("test_*.py")):
        for where, text in docstrings(path):
            for match in CITATION.finditer(text):
                rows.append((path.name, where, match.group(1), int(match.group(2))))
    return rows


def test_every_citation_lands_on_a_line_a_reader_can_read() -> None:
    tracked = _tracked()
    resolve_one = _repo_resolver(tracked, _index(tracked))
    offenders: list[str] = []
    for path in sorted(TESTS.glob("test_*.py")):
        for where, text in docstrings(path):
            offenders.extend(_offenders(text, f"{path.name}::{where}", resolve_one))
    assert not offenders, "test docstrings cite lines nobody can read:\n" + "\n".join(offenders)


def test_the_scan_finds_the_population_it_claims() -> None:
    rows = _corpus_citations()
    assert len(rows) >= 45, f"only {len(rows)} citations found; the scan has gone blind"
    targets = {resolve(token, _tracked(), _index(_tracked())) for _, _, token, _ in rows}
    targets.discard(None)
    assert len(targets) >= 12, f"citations resolved to only {sorted(t for t in targets if t)}"


def test_the_repaired_citations_still_name_what_the_sentence_claims() -> None:
    missing: list[str] = []
    for path, line, needle in REPAIRED:
        body = (REPO / path).read_text(encoding="utf-8", errors="replace").splitlines()
        if not 0 < line <= len(body):
            missing.append(f"{path}:{line} is outside the file")
        elif needle not in body[line - 1]:
            missing.append(f"{path}:{line} no longer contains {needle!r}: {body[line - 1].strip()!r}")
    assert not missing, "a re-aimed citation has drifted again:\n" + "\n".join(missing)


def test_the_roster_names_citations_the_corpus_really_makes() -> None:
    """The ten pinned pairs must be citations some docstring actually writes."""
    tracked = _tracked()
    index = _index(tracked)
    own = Path(__file__).name
    cited = {
        (resolve(token, tracked, index), line)
        for name, _, token, line in _corpus_citations()
        if name != own
    }
    stale = [f"{path}:{line}" for path, line, _ in REPAIRED if (path, line) not in cited]
    assert not stale, "the roster pins citations no docstring makes: " + ", ".join(stale)


def test_the_scan_flags_blank_out_of_range_and_dangling(tmp_path: Path) -> None:
    target = tmp_path / "leaf.py"
    target.write_text("one\n\ntwo\n", encoding="utf-8")
    text = "see ``leaf.py:2``, ``leaf.py:9`` and ``gone.py:1``"
    bad = _offenders(text, "synthetic", lambda token: target if token == "leaf.py" else None)
    assert len(bad) == 3, bad
    assert "blank line" in bad[0], bad
    assert "outside" in bad[1], bad
    assert "does not resolve" in bad[2], bad


def test_a_readable_citation_raises_nothing(tmp_path: Path) -> None:
    target = tmp_path / "leaf.py"
    target.write_text("one\n\ntwo\n", encoding="utf-8")
    assert _offenders("see ``leaf.py:3``", "synthetic", lambda token: target) == []
