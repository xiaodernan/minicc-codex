"""跨域残留：配置解析与离线评测报告——不属于 agent/tools/task/llm/session 任一域。

M8-T6 把 test_core.py 按 domain 拆成 test_core_{agent,tools,task,llm,session}.py；本文件主题的 minicc.config 与 minicc.benchmarks 不属于任一领域，硬塞会让文件名说谎。测试本体逐字搬迁，未改断言。"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from minicc.benchmarks import build_report, load_tasks, markdown_report
from minicc.config import load_config


def test_offline_benchmark_report_has_exact_fixtures_and_no_fabricated_results() -> None:
    tasks = load_tasks()
    report = build_report(tasks)
    assert len(tasks) == 30
    assert report["executed_count"] == 0
    assert report["metrics"]["pass_at_1"] is None
    assert all(item["status"] == "not_run" and item["cost_usd"] is None for item in report["results"])
    assert "N/A" in markdown_report(report)


def test_config_file_accepts_boolean_yolo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "api_key": "sk-test-config",
                "base_url": "https://example.test/v1",
                "model": "test-model",
                "yolo": True,
                "sandbox": "host",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    monkeypatch.delenv("MINICC_MODEL", raising=False)
    monkeypatch.delenv("MINICC_YOLO", raising=False)
    config = load_config()
    assert config.api_key == "sk-test-config"
    assert config.base_url == "https://example.test/v1"
    assert config.model == "test-model"
    assert config.yolo is True


def test_config_ignores_legacy_execution_budget_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-config")
    monkeypatch.delenv("MINICC_MAX_TURNS", raising=False)
    assert load_config().max_turns is None

    monkeypatch.setenv("MINICC_MAX_TURNS", "0")
    assert load_config().max_turns is None
    monkeypatch.setenv("MINICC_MAX_TURNS", "7")
    assert load_config().max_turns is None


def test_config_always_disables_task_duration_and_tool_count_budgets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.setenv("MINICC_API_KEY", "sk-runtime-guard-test")
    monkeypatch.setenv("MINICC_MAX_DURATION_SECONDS", "12.5")
    monkeypatch.setenv("MINICC_MAX_TOOL_CALLS", "17")
    config = load_config()
    assert config.max_duration_seconds is None
    assert config.max_tool_calls is None
