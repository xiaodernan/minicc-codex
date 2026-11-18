# -*- coding: utf-8 -*-
"""The operator backfill tool stays alive: honest failure paths, honest capture.

References ``scripts/evidence_backfill.py`` - the one-liner that keeps this file
in the audience floor, with real behavior underneath it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "evidence_backfill.py"
assert SCRIPT.is_file(), "scripts/evidence_backfill.py must exist for this audience to exist"


def _load():
    spec = importlib.util.spec_from_file_location("evidence_backfill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scripts_evidence_backfill_py_refuses_a_non_numeric_run_id():
    module = _load()
    with pytest.raises(SystemExit):
        module.main(["--run-id", "abc123"])


def test_unreachable_backend_fails_honestly(monkeypatch, capsys):
    import urllib.request

    def _hang(*args, **kwargs):
        raise TimeoutError("simulated unreachable gate")

    monkeypatch.setattr(urllib.request, "urlopen", _hang)
    module = _load()

    code = module.main(["--run-id", "44229273754"])

    assert code == 1
    out = capsys.readouterr().out
    assert "evidence backfill failed" in out


def test_invalid_json_body_fails_honestly(monkeypatch, capsys):
    import io
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Response(b"<not json>"))
    module = _load()

    code = module.main(["--run-id", "1"])

    assert code == 1
    assert "failed" in capsys.readouterr().out


def test_successful_backfill_prints_the_capture_line(monkeypatch, capsys):
    import io
    import json
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    payload = {
        "present": True,
        "latest": {
            "run_id": 44229273754,
            "conclusion": "success",
            "job_name": "PR eval gate",
            "head_sha": "2a23ec3a6ce7821fc76587fe7d7a9bf34b810c5d",
        },
        "entries": [],
    }

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: _Response(json.dumps(payload).encode("utf-8")),
    )
    module = _load()

    code = module.main(["--run-id", "44229273754"])

    assert code == 0
    out = capsys.readouterr().out
    assert "captured run 44229273754" in out
    assert "conclusion=success" in out
