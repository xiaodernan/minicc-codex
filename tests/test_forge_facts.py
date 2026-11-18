# -*- coding: utf-8 -*-
"""The forge-facts generator stays honest: real data in, marked gaps out, nothing invented."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "forge_facts.py"
assert SCRIPT.is_file(), "scripts/forge_facts.py must exist for this audience to exist"


def _load():
    spec = importlib.util.spec_from_file_location("forge_facts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "minicc-cloud").mkdir()

    def git(*args):
        import subprocess

        subprocess.check_call(
            ["git", *args], cwd=str(repo),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    git("init", "-q")
    git("config", "user.email", "fixture@localhost")
    git("config", "user.name", "fixture")
    git("config", "core.autocrlf", "false")
    (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-q", "-m", "seed: initial fixture commit")

    (repo / "docs" / "latest.json").write_text(json.dumps({
        "head": "abc1234",
        "generated_at": "2026-11-19T00:00:00.000Z",
        "total_commits": 1986,
        "roadmap_batches": 493,
        "almanac_chapters": 61,
        "test_files": 746,
        "tracked_files": 1156,
        "roadmap_lines": 55786,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    matrix = (
        "# Cache affinity matrix\n"
        "same family warm call: 8,362/8,566 = 97.6% steady.\n"
        "fresh agent end-to-end: 71.6% and a resume read-only revisit 48.0%.\n"
        "TTL note: 150 s of silence evicts the shard; keeper now defaults to 60 s.\n"
        "nothing else worth capturing.\n"
    )
    (repo / "docs" / "CACHE_AFFINITY_MATRIX.md").write_text(matrix, encoding="utf-8")

    load = (
        "# Load testing\n"
        "First wave: 33,600 requests, zero non-2xx.\n"
        "Full day: 59,070 requests, zero non-2xx.\n"
        "Second wave added 25,470 requests.\n"
        "Credential stuffing: 400/400 forged tokens -> 401.\n"
    )
    (repo / "docs" / "LOAD_TESTING.md").write_text(load, encoding="utf-8")

    pom = (
        "<project><modules><module>minicc-cloud-gateway</module>"
        "<module>minicc-cloud-evidence</module><module>minicc-cloud-registry</module>"
        "</modules></project>\n"
    )
    (repo / "minicc-cloud" / "pom.xml").write_text(pom, encoding="utf-8")
    return repo


def test_generate_facts_includes_real_numbers(tmp_path):
    module = _load()
    repo = _fixture_repo(tmp_path)
    text = module.generate_facts(repo, chapter="LXII")
    assert "abc1234" in text
    assert '"total_commits": 1986' in text
    assert "97.6%" in text and "71.6%" in text and "48.0%" in text
    assert "59,070" in text and "33,600" in text and "400/400" in text
    assert "minicc-cloud-gateway" in text and "minicc-cloud-evidence" in text
    assert "seed: initial fixture commit" in text
    assert "Almanac LXII" in text


def test_missing_files_report_as_gaps_not_crashes(tmp_path):
    module = _load()
    repo = tmp_path / "bare"
    repo.mkdir()
    text = module.generate_facts(repo, chapter="LXII")
    assert "(fact pack missing)" in text
    assert "(git log unavailable)" in text
    assert "(pom missing)" in text
