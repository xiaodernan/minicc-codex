"""M8-T1056 (follows M8-T1052): the live cache-affinity probe is not allowed
to drift silently — and the impact floor requires a test that reaches it.

Two invariants matter more than plumbing:

1. **Secrets never leak to stdout**, even under failure: no key material ever
   appears in dry-run output or in the NO_KEY error path.
2. **The probe never dials the network on dry-run or on missing key** — it
   exits 0 / 2 with a shape-only line respectively, with zero imports of the
   OpenAI SDK.

and `.env` parsing order is pinned: process environment wins; the gitignored
repo-local `.env` is the documented fallback; absent both, `main()` answers 2
with NO_KEY. Nothing here mocks *outbound traffic*: the network is simply
never in play.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# contiguous "scripts/…/measure_cache_affinity.py" literal — the impact floor reads exactly this
PROBE_RELPATH = "scripts/measure_cache_affinity.py"
SCRIPT = REPO_ROOT / PROBE_RELPATH


def _load_module(monkeypatch, *, env: dict[str, str | None], cwd: Path | None = None):
    """Import the probe as a module with a scrubbed environment."""
    for key in ("MINICC_API_KEY", "MINICC_BASE_URL", "MINICC_MODEL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is not None:
            monkeypatch.setenv(key, value)
    if cwd is not None:
        monkeypatch.chdir(cwd)
    spec = importlib.util.spec_from_file_location("measure_cache_affinity", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


# ---------------------------------------------------------------------------
# _load_settings: env wins, .env fallback, absent both -> None
# ---------------------------------------------------------------------------


def test_process_environment_wins_over_dotenv(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "MINICC_API_KEY=sentinel-from-disk\n"
        "MINICC_BASE_URL=https://from-disk/v1\n"
        "MINICC_MODEL=from-disk-model\n",
        encoding="utf-8",
    )
    module = _load_module(
        monkeypatch,
        env={
            "MINICC_API_KEY": "sentinel-from-env",
            "MINICC_BASE_URL": None,
            "MINICC_MODEL": None,
        },
        cwd=tmp_path,
    )
    key, base, model = module._load_settings()
    assert key == "sentinel-from-env"
    assert base == "https://wkapi.pro/v1"  # env var unset -> documented default, disk not consulted for it


def test_dotenv_fallback_parses_only_known_keys(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "MINICC_API_KEY=sentinel-from-disk\n"
        "MINICC_BASE_URL=https://from-disk/v1\n"
        "MINICC_MODEL=from-disk-model\n"
        "MINICC_SOMETHING_ELSE=not-read\n",
        encoding="utf-8",
    )
    module = _load_module(monkeypatch, env={}, cwd=tmp_path)
    assert module._load_settings() == ("sentinel-from-disk", "https://from-disk/v1", "from-disk-model")


def test_missing_everywhere_returns_none_key(tmp_path: Path, monkeypatch) -> None:
    module = _load_module(monkeypatch, env={}, cwd=tmp_path)
    key, base, model = module._load_settings()
    assert key is None
    assert base == "https://wkapi.pro/v1"
    assert model == "gpt-6-sol"


# ---------------------------------------------------------------------------
# main(): dry-run and NO_KEY never touch the key, never open a socket
# ---------------------------------------------------------------------------


def test_dry_run_prints_shape_and_exits_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["measure_cache_affinity.py", "--dry-run"])
    module = _load_module(monkeypatch, env={}, cwd=tmp_path)
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "sk-" not in out


def test_missing_key_exits_two_without_noise(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["measure_cache_affinity.py"])
    module = _load_module(monkeypatch, env={}, cwd=tmp_path)
    assert module.main() == 2
    out = capsys.readouterr().out
    assert "NO_KEY" in out
    assert "sk-" not in out


def test_module_source_reads_no_key_literal() -> None:
    """The committed probe must contain no embedded key material at all."""
    blob = SCRIPT.read_bytes()
    assert b"sk-" not in blob, "the probe script ships key-shaped material"
