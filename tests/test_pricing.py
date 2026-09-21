"""M4-T4: USD pricing table, cost_usd accounting, and end-to-end $/task.

Covers the acceptance criteria for the pricing milestone:
  * fixed usage → cost_usd exact to 1e-6;
  * an unknown model is honestly None (never a guessed price);
  * the cache-hit portion is billed at the discounted cache_read rate;
  * a fake-provider run with an explicit price yields a non-null
    cost_per_success_usd in the benchmark report;
  * neither the benchmark results file nor a task snapshot leaks the api_key.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc import pricing
from minicc.benchmarks import build_report, run_benchmark
from minicc.pricing import ModelPrice, cost_usd, load_price_table, price_for
from minicc.task_manager import TaskRecord


def test_cost_usd_exact_to_one_microdollar() -> None:
    # gpt-4o: input 2.50, output 10.00 per 1M tokens.
    usage = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
    expected = (1000 * 2.50 + 500 * 10.00) / 1_000_000  # 0.0075
    assert cost_usd("gpt-4o", usage) == pytest.approx(expected, abs=1e-6)
    assert cost_usd("gpt-4o", usage) == pytest.approx(0.0075, abs=1e-6)


def test_cost_usd_unknown_model_is_none() -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    assert cost_usd("gpt-5.6-terra", usage) is None
    assert cost_usd("totally-made-up-model", usage) is None
    assert cost_usd("", usage) is None
    assert price_for("gpt-5.6-terra") is None


def test_cost_usd_longest_prefix_wins() -> None:
    # "gpt-4o-mini" must not be priced as "gpt-4o".
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0}
    mini = cost_usd("gpt-4o-mini-2024-07-18", usage)
    full = cost_usd("gpt-4o-2024-08-06", usage)
    assert mini == pytest.approx(0.15, abs=1e-6)
    assert full == pytest.approx(2.50, abs=1e-6)
    assert mini != full


def test_cache_hit_billed_at_discounted_read_rate() -> None:
    # 1000 prompt tokens, 400 of them cache hits. The 600 miss tokens pay the
    # full input rate; the 400 hit tokens pay the cheaper cache_read rate.
    usage = {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 400, "completion_tokens": 0}
    discounted = cost_usd("gpt-4o", usage)
    undiscounted = cost_usd("gpt-4o", {"prompt_tokens": 1000, "completion_tokens": 0})
    expected = (600 * 2.50 + 400 * 1.25) / 1_000_000  # 0.002
    assert discounted == pytest.approx(expected, abs=1e-6)
    assert undiscounted == pytest.approx(0.0025, abs=1e-6)
    assert discounted < undiscounted


def test_cache_write_billed_separately() -> None:
    usage = {
        "prompt_tokens": 0,
        "prompt_cache_write_tokens": 1000,
        "completion_tokens": 0,
    }
    # gpt-4o cache_write == input == 2.50 per 1M.
    assert cost_usd("gpt-4o", usage) == pytest.approx(0.0025, abs=1e-6)


def test_pricing_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MINICC_PRICING_JSON",
        json.dumps({"internal-model": {"input": 1.0, "output": 4.0, "cache_read": 0.5}}),
    )
    table = load_price_table()
    assert "internal-model" in table
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0}
    assert cost_usd("internal-model-v2", usage, table=table) == pytest.approx(1.0, abs=1e-6)


def test_malformed_pricing_override_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_PRICING_JSON", "{not json")
    table = load_price_table()
    assert table == pricing.DEFAULT_PRICE_TABLE
    monkeypatch.setenv("MINICC_PRICING_JSON", json.dumps({"bad": {"output": 1.0}}))
    # Missing "input" → entry dropped, never raises.
    assert "bad" not in load_price_table()


def test_price_from_mapping_defaults_cache_to_input() -> None:
    price = ModelPrice.from_mapping({"input": 2.0, "output": 8.0})
    assert price is not None
    assert price.cache_read_per_mtok == 2.0
    assert price.cache_write_per_mtok == 2.0
    assert ModelPrice.from_mapping({"output": 8.0}) is None


def test_cost_usd_handles_missing_and_negative_counters() -> None:
    assert cost_usd("gpt-4o", {}) == pytest.approx(0.0, abs=1e-9)
    assert cost_usd("gpt-4o", None) is None
    # Negative counters are clamped, never producing a negative cost.
    assert cost_usd("gpt-4o", {"prompt_tokens": -5, "completion_tokens": -3}) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# end-to-end: fake provider + explicit price → cost_per_success_usd
# ---------------------------------------------------------------------------


def _service_config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="super-secret-key-do-not-leak",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )


def test_fake_provider_run_yields_non_null_cost_per_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON",
        json.dumps({"test-model": {"input": 3.0, "output": 15.0, "cache_read": 0.3}}),
    )
    from minicc.web import AgentService

    original_init = AgentService.__init__

    def patched_init(self, workspace, config, *args, **kwargs):
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)
    monkeypatch.setattr("minicc.config.load_config", _service_config)

    tasks = [{
        "id": "priced-task",
        "category": "verify",
        "prompt": "回答任意内容。",
        "verify_command": "python -c \"print('ok')\"",
    }]
    results_path = tmp_path / "results.json"
    results = run_benchmark(tasks, workspace=tmp_path, results_path=results_path)
    assert results[0]["status"] == "completed"
    assert results[0]["passed"] is True
    # The fake provider now reports a prompt/completion split, so the row cost
    # is a real positive number rather than a null or zero placeholder.
    assert results[0]["cost_usd"] is not None
    assert results[0]["cost_usd"] > 0

    report = build_report(tasks, results)
    assert report["metrics"]["cost_per_success_usd"] is not None
    assert report["metrics"]["cost_per_success_usd"] > 0
    assert report["metrics"]["cost_available"] == 1


def test_results_file_does_not_leak_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON",
        json.dumps({"test-model": {"input": 3.0, "output": 15.0}}),
    )
    from minicc.web import AgentService

    original_init = AgentService.__init__

    def patched_init(self, workspace, config, *args, **kwargs):
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)
    monkeypatch.setattr("minicc.config.load_config", _service_config)

    results_path = tmp_path / "results.json"
    run_benchmark([{"id": "leak-check", "prompt": "hi"}], workspace=tmp_path, results_path=results_path)
    text = results_path.read_text(encoding="utf-8")
    assert "super-secret-key-do-not-leak" not in text
    assert "api_key" not in text


def test_task_snapshot_carries_cost_without_api_key() -> None:
    task = TaskRecord(task_id="cost-snap", session_id="s", message="hi", allow_changes=False, model="gpt-4o")
    task.transition_status("running")
    task.update_usage({"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500})
    snapshot = task.snapshot()
    assert snapshot["cost_usd"] == pytest.approx(0.0075, abs=1e-6)
    blob = json.dumps(snapshot, default=str)
    assert "api_key" not in blob
    assert "super-secret" not in blob


def test_task_snapshot_cost_is_none_for_unpriced_model() -> None:
    task = TaskRecord(task_id="free-snap", session_id="s", message="hi", allow_changes=False, model="gpt-5.6-terra")
    task.update_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    assert task.snapshot()["cost_usd"] is None
