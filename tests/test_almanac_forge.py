# -*- coding: utf-8 -*-
"""The almanac forge stays an honest StateGraph: real verify, real bounded repair.

Model calls are stubbed; the graph, the verify contract and the ledger
artifact are the real thing under test.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "almanac_forge.py"
assert SCRIPT.is_file(), "scripts/almanac_forge.py must exist for this audience to exist"


def _load():
    spec = importlib.util.spec_from_file_location("almanac_forge", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ZH_BODY = ("卷六十一：锻造台——大模型不是传送门，是工人。" * 60).strip()
EN_BODY = ("Volume Sixty-One: the forge. The model is not a portal, it is a worker. " * 12).strip()
VALID = {"zh": ZH_BODY, "en": EN_BODY}
DIRTY_EN = {"zh": ZH_BODY, "en": EN_BODY + " 这句话含中文"}


def _stub_runtime(module, responses, usage):
    """Return an _load_runtime replacement that reaches the graph but never the wire."""
    from minicc.agent.graph import GraphNode, StateGraph
    from minicc.agent.state import AgentState, Budget
    from minicc.oracle_common import parse_json_object

    calls = {"n": 0}

    def fake_call_model(*, config, prompt, max_tokens=2600, temperature=0.2, response_format=None, request_timeout=60.0):
        calls["n"] += 1
        idx = min(calls["n"] - 1, len(responses) - 1)
        return {"text": responses[idx], "usage": usage, "model": "stub-model"}

    def fake_load_config(*, workspace=None):
        return object()

    def fake_load_runtime():
        return fake_load_config, fake_call_model, parse_json_object, GraphNode, StateGraph, AgentState, Budget

    return fake_load_runtime, calls


def _facts(tmp_path: Path) -> Path:
    facts = tmp_path / "facts.txt"
    facts.write_text("measured fact: 24 calls, 97.6% steady hit, one cold call per family.\n", encoding="utf-8")
    return facts


def test_forge_passes_first_try(tmp_path, monkeypatch):
    module = _load()
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cached_tokens": 90}
    fake, calls = _stub_runtime(module, [json.dumps(VALID, ensure_ascii=False)], usage)
    monkeypatch.setattr(module, "_load_runtime", lambda: fake())
    out = tmp_path / "chapter.json"
    result = module.forge(_facts(tmp_path), chapter="LXI", title_zh="锻造台", title_en="The Forge", out=out)
    assert calls["n"] == 1
    assert result["status"] == "passed"
    assert result["verification"]["attempts"] == 1
    assert result["written_by"] == "stub-model"
    assert result["usage"]["cached_tokens"] == 90
    assert out.is_file()


def test_forge_repairs_cjk_in_en_then_passes(tmp_path, monkeypatch):
    module = _load()
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    fake, calls = _stub_runtime(
        module,
        [json.dumps(DIRTY_EN, ensure_ascii=False), json.dumps(VALID, ensure_ascii=False)],
        usage,
    )
    monkeypatch.setattr(module, "_load_runtime", lambda: fake())
    out = tmp_path / "chapter.json"
    result = module.forge(_facts(tmp_path), chapter="LXI", title_zh="锻造台", title_en="The Forge", out=out)
    assert calls["n"] == 2
    assert result["status"] == "passed"
    assert result["verification"]["attempts"] == 2


def test_forge_fails_after_repeated_cjk_leak(tmp_path, monkeypatch):
    module = _load()
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    fake, calls = _stub_runtime(module, [json.dumps(DIRTY_EN, ensure_ascii=False)], usage)
    monkeypatch.setattr(module, "_load_runtime", lambda: fake())
    with pytest.raises(RuntimeError):
        module.forge(_facts(tmp_path), chapter="LXI", title_zh="锻造台", title_en="The Forge",
                     out=tmp_path / "chapter.json")
    assert calls["n"] >= 2


def test_forge_missing_key_does_not_crash_it_fails_loudly(tmp_path, monkeypatch):
    module = _load()
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    zh_only = json.dumps({"zh": ZH_BODY}, ensure_ascii=False)
    fake, calls = _stub_runtime(module, [zh_only], usage)
    monkeypatch.setattr(module, "_load_runtime", lambda: fake())
    with pytest.raises(RuntimeError) as excinfo:
        module.forge(_facts(tmp_path), chapter="LXII", title_zh="锻造台", title_en="The Forge",
                     out=tmp_path / "chapter.json")
    assert "KeyError" not in str(excinfo.value)
    assert calls["n"] >= 2


def test_verify_chapter_contract():
    module = _load()
    ok, reasons = module.verify_chapter({"zh": ZH_BODY, "en": EN_BODY})
    assert ok and not reasons
    ok, reasons = module.verify_chapter({"zh": ZH_BODY, "en": EN_BODY + " 中文"})
    assert not ok and any("CJK" in r for r in reasons)
    ok, reasons = module.verify_chapter({"zh": ZH_BODY, "en": EN_BODY, "extra": 1})
    assert not ok and any("keys" in r for r in reasons)
    ok, reasons = module.verify_chapter({"zh": "x", "en": "y"})
    assert not ok and any("too short" in r for r in reasons)
    ok, reasons = module.verify_chapter({"zh": ZH_BODY + "<script>x</script>", "en": EN_BODY})
    assert not ok and any("script" in r.lower() for r in reasons)
