"""M4-T7: retrieval decision gate (lexical hit-rate baseline).

The roadmap fixes the decision rule: only introduce a local embedding model when
the lexical baseline's recall@5 < 0.6, and otherwise write down "不引入向量检索"
and stop investing. These tests pin the metric math, the dataset validation, the
decision thresholds, and the `--suite retrieval` wiring — including asserting the
committed real dataset actually clears the floor (so the written conclusion is
backed by a reproducible number, not a claim).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc import benchmarks
from minicc.benchmarks import (
    DEFAULT_RETRIEVAL,
    REPO_ROOT,
    RETRIEVAL_RECALL_FLOOR,
    evaluate_retrieval,
    load_retrieval_cases,
    main,
    retrieval_decision,
)


# --- dataset loading / validation -----------------------------------------


def test_real_dataset_loads_and_is_wellformed():
    dataset = load_retrieval_cases(DEFAULT_RETRIEVAL)
    assert dataset["ks"] == [1, 5]
    assert len(dataset["cases"]) >= 12
    ids = [case["id"] for case in dataset["cases"]]
    assert len(ids) == len(set(ids))
    for case in dataset["cases"]:
        assert case["query"].strip()
        assert all(not t.startswith("/") for t in case["targets"])


def test_load_rejects_bad_datasets(tmp_path):
    def _write(payload):
        path = tmp_path / "ds.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    with pytest.raises(ValueError):
        load_retrieval_cases(_write([]))  # not a dict
    with pytest.raises(ValueError):
        load_retrieval_cases(_write({"cases": []}))  # empty
    with pytest.raises(ValueError):
        load_retrieval_cases(_write({"cases": [
            {"id": "a", "query": "q", "targets": ["x.py"]},
            {"id": "a", "query": "q2", "targets": ["y.py"]},  # dup id
        ]}))
    with pytest.raises(ValueError):
        load_retrieval_cases(_write({"cases": [
            {"id": "a", "query": "  ", "targets": ["x.py"]},  # blank query
        ]}))
    with pytest.raises(ValueError):
        load_retrieval_cases(_write({"cases": [
            {"id": "a", "query": "q", "targets": ["/abs/x.py"]},  # absolute
        ]}))
    with pytest.raises(ValueError):
        load_retrieval_cases(_write({"cases": [
            {"id": "a", "query": "q", "targets": ["../escape.py"]},  # escape
        ]}))
    with pytest.raises(ValueError):
        load_retrieval_cases(_write({"cases": [
            {"id": "a", "query": "q", "targets": []},  # empty targets
        ]}))
    with pytest.raises(ValueError):
        load_retrieval_cases(_write({"ks": [0], "cases": [
            {"id": "a", "query": "q", "targets": ["x.py"]},
        ]}))


# --- metric math on a synthetic workspace ---------------------------------


def _synthetic_workspace(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pricing.py").write_text(
        "def cost_usd(model, usage):\n    return 0.0\n", encoding="utf-8")
    (tmp_path / "unrelated.py").write_text(
        "def helper():\n    return 'nothing relevant here'\n", encoding="utf-8")
    return tmp_path


def test_evaluate_retrieval_metrics_and_misses(tmp_path):
    ws = _synthetic_workspace(tmp_path)
    cases = [
        {"id": "c1", "query": "cost_usd 美元成本", "targets": ["pricing.py"]},
        {"id": "c2", "query": "cost_usd model usage", "targets": ["pricing.py"]},
        {"id": "c3", "query": "zzzqqq nonexistent token", "targets": ["unrelated.py"]},
    ]
    report = evaluate_retrieval(cases, workspace=ws, ks=(1, 5))
    assert report["case_count"] == 3
    metrics = report["metrics"]
    # c1/c2 must localize pricing.py; c3 is a deliberate miss.
    by_id = {row["id"]: row for row in report["results"]}
    assert by_id["c1"]["first_relevant_rank"] == 1
    assert by_id["c3"]["first_relevant_rank"] is None
    assert by_id["c3"]["recall@5"] == 0.0
    # recall@5 can only grow with k, and the miss keeps both below 1.0.
    assert metrics["recall@5"] >= metrics["recall@1"]
    assert 0.0 < metrics["recall@1"] <= 1.0
    assert 0.0 < metrics["mrr"] <= 1.0
    # two hits out of three at rank 1 → recall@1 == mrr == 2/3.
    assert metrics["recall@1"] == pytest.approx(2 / 3, abs=1e-4)
    assert metrics["mrr"] == pytest.approx(2 / 3, abs=1e-4)


def test_evaluate_retrieval_recall_counts_partial_multi_target(tmp_path):
    ws = tmp_path
    (ws / "a.py").write_text("def alpha_shared_marker():\n    pass\n", encoding="utf-8")
    (ws / "b.py").write_text("def beta_shared_marker():\n    pass\n", encoding="utf-8")
    cases = [{"id": "m", "query": "alpha_shared_marker", "targets": ["a.py", "b.py"]}]
    report = evaluate_retrieval(cases, workspace=ws, ks=(1, 5))
    # Only a.py matches the query, so multi-target recall is at most 1/2.
    assert report["results"][0]["recall@5"] <= 0.5


# --- decision rule ---------------------------------------------------------


def test_retrieval_decision_thresholds():
    assert "不引入向量检索" in retrieval_decision(0.9)
    assert "不引入向量检索" in retrieval_decision(RETRIEVAL_RECALL_FLOOR)  # == floor passes
    below = retrieval_decision(0.59)
    assert "embedding" in below and "A/B" in below
    assert "无法判定" in retrieval_decision(None)


def test_real_dataset_clears_floor_backing_the_written_conclusion():
    dataset = load_retrieval_cases(DEFAULT_RETRIEVAL)
    workspace = (REPO_ROOT / dataset["workspace"]).resolve()
    report = evaluate_retrieval(dataset["cases"], workspace=workspace, ks=dataset["ks"])
    recall5 = report["metrics"]["recall@5"]
    assert recall5 >= RETRIEVAL_RECALL_FLOOR, (
        f"committed dataset recall@5={recall5} fell below the floor; the "
        "「不引入向量检索」 conclusion is no longer backed by the baseline"
    )
    assert "不引入向量检索" in retrieval_decision(recall5)


# --- CLI wiring ------------------------------------------------------------


def test_main_suite_retrieval_writes_reports(tmp_path):
    ws = _synthetic_workspace(tmp_path / "ws")
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "pricing.py").write_text("def cost_usd():\n    return 0\n", encoding="utf-8")
    dataset = tmp_path / "ds.json"
    # An absolute workspace path overrides the REPO_ROOT join in pathlib.
    dataset.write_text(json.dumps({
        "workspace": str(ws),
        "ks": [1, 5],
        "cases": [{"id": "c1", "query": "cost_usd", "targets": ["pricing.py"]}],
    }), encoding="utf-8")
    json_out = tmp_path / "r.json"
    md_out = tmp_path / "r.md"
    code = main(["--suite", "retrieval", "--fixtures", str(dataset),
                 "--json-out", str(json_out), "--markdown-out", str(md_out)])
    assert code == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["case_count"] == 1
    assert payload["metrics"]["recall@1"] == 1.0
    assert "decision" in payload
    md = md_out.read_text(encoding="utf-8")
    assert "Retrieval Hit-Rate" in md and "结论" in md


def test_main_suite_retrieval_bad_dataset_returns_2(tmp_path):
    dataset = tmp_path / "bad.json"
    dataset.write_text(json.dumps({"cases": []}), encoding="utf-8")
    code = main(["--suite", "retrieval", "--fixtures", str(dataset),
                 "--json-out", str(tmp_path / "o.json"),
                 "--markdown-out", str(tmp_path / "o.md")])
    assert code == 2
