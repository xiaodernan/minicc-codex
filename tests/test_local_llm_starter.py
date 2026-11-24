"""M8-T1338: the offline-LLM starter must prove inference, not just /api/tags.

Two real defects this pins:
1. `/api/tags` answers 200 even in the crashing CUDA mode, so READY based on
   tags alone lied; the starter must run a real chat request.
2. PowerShell comments are `#`, not `/* */` — the old catch block errored when
   Ollama was not already listening (a path never exercised while tags answered).
"""

from __future__ import annotations

from pathlib import Path

STARTER = Path(__file__).resolve().parents[1] / "scripts" / "start_local_llm.ps1"


def _text() -> str:
    return STARTER.read_text(encoding="utf-8")


def test_starter_proves_inference_not_only_tags() -> None:
    body = _text()
    assert "chat/completions" in body, "READY must be gated on a real inference request"
    assert "Invoke-InferenceProbe" in body
    # The already-listening path must also probe inference, not just tags.
    already = body.split("Already listening?")[1].split("Write-Host \"Starting")[0]
    assert "Invoke-InferenceProbe" in already, "existing serve was accepted on tags alone"


def test_no_c_style_comments_in_powershell() -> None:
    body = _text()
    assert "/*" not in body and "*/" not in body, "PowerShell comments are #, not /* */"


def test_cpu_mode_is_persisted_at_user_scope() -> None:
    body = _text()
    assert '"OLLAMA_NUM_GPU", "0", "User"' in body
    assert '"OLLAMA_VULKAN", "false", "User"' in body


def test_fresh_start_path_still_exists() -> None:
    body = _text()
    assert "Start-Process" in body and "-ArgumentList \"serve\"" in body
    assert "nothing listening" in body.lower() or "not running" in body.lower()
