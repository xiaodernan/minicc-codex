"""M8-T535（第五百一十七批）：同一份报告放在比较的两边，差值就不是量出来的 0。

现场是 nightly 的那一步：`.github/workflows/ci.yml` 把
`--baseline output/nightly-v2.json --variant output/nightly-v2.json`——**同一个路径
放在两边**——交给 `minicc.benchmarks compare`，后者派发到 `bench_compare.main`
（`minicc/benchmarks.py:688-689`）。比较器在那种输入下把六个「移动」字段写成 `0.0`，
`pass_at_1_delta_ci` 还写出一条 ±0.3482 的 Newcombe 区间（同一个样本和自己比的产物），
上传的 `output/nightly-compare.json` 里这些行读起来像「准确率与延迟都没有劣化」。

campaign 的口径：一次**没有做**的比较，不许写成**做了、答案是零**（与第五百一十五批
`mtime = 0.0`、第五百一十六批「我没跑起来」压成「我抓到了」同形）。被清掉的只是
「两侧之间的移动」——两侧各自的数是真量到的，腿二钉住它们还在。

判据为什么是**字节**而不是报告里的时钟：`probe_535d.py`（2026-10-29 本机）实测
`build_report` 连开 50 次只得到 **4** 个不同的 `generated_at_epoch`——相邻 49 对里
**46 对相等**（这台机器的 `time.time()` 2000 次紧循环只跨了 2 个刻度）。所以
「两侧时间戳相同」证明不了「两侧是同一次测量」：按戳清差值会把真实 A/B 一起抹掉，
那是遮蔽回归，比本批要修的谎更糟。能证明「一边是另一边的同一个文件」的，只有
CLI 手上那两份字节的相等。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc import bench_compare
from minicc.bench_compare import compare_reports, main
from minicc.benchmarks import build_report

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"

#: The six keys that claim "the variant moved relative to the baseline".  Spelled
#: out here rather than imported: they are the published JSON's own vocabulary, and
#: a gate that cannot import a name must still be able to say the name is missing.
MOVEMENT_FIELDS = (
    "pass_at_1_delta",
    "pass_at_1_delta_ci",
    "cost_per_success_delta",
    "cost_per_success_delta_ci",
    "latency_p50_delta_ms",
    "latency_p95_delta_ms",
)


def _report(*, p95_unit: float = 826_000.0, pass_every: int = 2) -> dict:
    tasks = [{"id": f"t{i}", "category": "write" if i < 6 else "test-fix"} for i in range(12)]
    results = [
        {
            "task_id": f"t{i}",
            "status": "completed",
            "passed": i % pass_every == 0,
            "latency_ms": p95_unit * (i + 1) / 12,
            "cost_usd": 0.02,
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        }
        for i in range(12)
    ]
    return build_report(tasks, results)


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _hand_p95(unit: float) -> float:
    """R-7 p95 of ``unit * (i+1) / 12`` for i in 0..11, by hand.

    position = 11 * 0.95 = 10.45 -> v[10] + 0.45 * (v[11] - v[10]), v[i] = unit*(i+1)/12.
    """
    lower = unit * 11 / 12
    return lower + (unit - lower) * 0.45


def _run(tmp_path: Path, baseline: Path, variant: Path, *extra: str) -> tuple[int, dict]:
    out = tmp_path / "nightly-compare.json"
    code = main([
        "--baseline", str(baseline),
        "--variant", str(variant),
        "--repeat", "2",
        "--bootstrap-iterations", "60",
        "--json-out", str(out),
        *extra,
    ])
    return code, json.loads(out.read_text(encoding="utf-8"))


def test_a_self_compare_does_not_publish_movement_as_measured(tmp_path: Path) -> None:
    one = _write(tmp_path, "nightly-v2.json", _report())
    _code, comparison = _run(tmp_path, one, one)
    wrong = {key: comparison.get(key) for key in MOVEMENT_FIELDS
             if comparison.get(key) is not None}
    assert not wrong, (
        f"两边是同一个文件，这些字段却写成了量出来的值：{wrong}——"
        "同一次比较里没有东西可减，None 才是诚实的值"
    )


def test_the_two_sides_themselves_still_read_measured_numbers(tmp_path: Path) -> None:
    """The anti-vacuity floor: None must come from "nothing to subtract".

    Without this leg the six fields could go None for the wrong reason - an empty
    alignment, a missing grader - and the batch's claim would be unfalsifiable.
    """
    one = _write(tmp_path, "nightly-v2.json", _report())
    _code, comparison = _run(tmp_path, one, one)
    assert comparison["aligned_task_count"] == 12, comparison["aligned_task_count"]
    for side in ("baseline", "variant"):
        block = comparison[side]
        assert block["pass_at_1"] is not None, f"{side} 自己的 pass@1 就没量到，这条门在骗人"
        assert block["latency_p95_ms"] is not None, f"{side} 自己的 p95 就没量到"
        assert block["cost_per_success_usd"] is not None, f"{side} 自己的 cost 就没量到"


def test_the_published_json_carries_the_verdict_about_the_two_sides(tmp_path: Path) -> None:
    one = _write(tmp_path, "nightly-v2.json", _report())
    _code, comparison = _run(tmp_path, one, one)
    assert "same_measurement" in comparison, (
        f"判决里没有「两侧是不是同一次测量」这一项，读者只能从一列 0.0 里猜：{sorted(comparison)}"
    )
    assert comparison["same_measurement"] is True, (
        f"两边是同一个文件，判决却没说是同一次测量：{comparison['same_measurement']!r}"
    )


def test_the_report_says_in_words_that_no_ab_ran(tmp_path: Path, capsys) -> None:
    one = _write(tmp_path, "nightly-v2.json", _report())
    _code, comparison = _run(tmp_path, one, one)
    said = [note for note in comparison["notes"] if "同一次测量" in note or "没有 A/B" in note]
    assert said, (
        f"上传的 JSON 里没有任何一句话说明这次比较没有 A/B，读者只剩一列 N/A 可读：{comparison['notes']}"
    )
    printed = capsys.readouterr().out
    assert "同一次测量" in printed, "人在终端上看到的 delta 表没有这句话——只有机器读的 JSON 知道"


def test_the_category_breakdown_does_not_keep_the_zeroes(tmp_path: Path) -> None:
    """The same claim, one level down: a per-category 0.0 reads as "that kind is fine".

    Six blanked top-level fields and a `categories` block full of structural zeroes is
    a report that still says every category held steady.
    """
    one = _write(tmp_path, "nightly-v2.json", _report())
    _code, comparison = _run(tmp_path, one, one)
    kept = {c: block["delta"] for c, block in comparison["categories"].items()
            if block["delta"] is not None}
    assert not kept, f"顶层差值清了，分类目里还留着 {kept}"
    for category, block in comparison["categories"].items():
        assert block["baseline_pass_at_1"] is not None, f"{category} 两侧各自的数被一并抹掉了"
        assert block["variant_pass_at_1"] is not None, f"{category} 两侧各自的数被一并抹掉了"


def test_a_real_ab_at_the_same_entry_still_measures_movement(tmp_path: Path) -> None:
    baseline = _report(p95_unit=400_000.0)
    variant = _report(p95_unit=900_000.0, pass_every=1)
    # Distinct stamps on purpose: leg 8 pins that the stamp is *not* the trigger, so
    # this leg must not depend on it - and on a coarse clock two build_report calls
    # back to back would otherwise share one tick (measured 46 of 49 pairs).
    variant["generated_at_epoch"] = baseline["generated_at_epoch"] + 3600.0
    base = _write(tmp_path, "a.json", baseline)
    var = _write(tmp_path, "b.json", variant)
    _code, comparison = _run(tmp_path, base, var)
    assert comparison["same_measurement"] is False, (
        f"两边是不同的文件，判决却说是同一次测量：{comparison['same_measurement']!r}"
    )
    assert comparison["latency_p95_delta_ms"] is not None
    assert comparison["latency_p95_delta_ms"] > 0, comparison["latency_p95_delta_ms"]
    assert comparison["pass_at_1_delta"] is not None
    assert comparison["pass_at_1_delta_ci"] is not None
    blank = [c for c, block in comparison["categories"].items() if block["delta"] is None]
    assert not blank, f"两边是不同的报告，这些类目的差值却没了：{blank}"


def test_a_copy_at_a_second_path_is_still_one_measurement(tmp_path: Path) -> None:
    """Byte identity, not textual path identity - a renamed copy is the same run.

    `cp nightly-v2.json candidate.json` is exactly what a reviewer would type, and it
    leaves the same structurally-zero movement behind.
    """
    blob = json.dumps(_report(), ensure_ascii=False)
    left = tmp_path / "nightly-v2.json"
    right = tmp_path / "candidate.json"
    left.write_text(blob, encoding="utf-8")
    right.write_text(blob, encoding="utf-8")
    _code, comparison = _run(tmp_path, left, right)
    assert comparison["same_measurement"] is True, (
        f"改名后的两个文件仍是同一份报告的字节，判决却没说是同一次测量：{comparison['same_measurement']!r}"
    )
    assert comparison["latency_p95_delta_ms"] is None


def test_two_runs_that_share_a_clock_tick_are_not_a_self_compare(tmp_path: Path) -> None:
    """The stamp is not an identity: measured 46/49 adjacent build_report pairs equal.

    If the fix triggers on ``generated_at_epoch`` equality it blanks a *real* A/B,
    which hides regressions - worse than the placeholder this batch removes.
    """
    baseline = _report(p95_unit=400_000.0, pass_every=2)
    variant = _report(p95_unit=900_000.0, pass_every=1)
    variant["generated_at_epoch"] = baseline["generated_at_epoch"]
    base = _write(tmp_path, "a.json", baseline)
    var = _write(tmp_path, "b.json", variant)
    assert json.loads(base.read_text(encoding="utf-8"))["generated_at_epoch"] == \
        json.loads(var.read_text(encoding="utf-8"))["generated_at_epoch"], "夹具失效"
    _code, comparison = _run(tmp_path, base, var)
    assert comparison["same_measurement"] is False, (
        "两侧时间戳相同但字节不同：这是两次读数相同刻度、不是同一次测量"
    )
    assert comparison["latency_p95_delta_ms"] == pytest.approx(_hand_p95(900_000.0) - _hand_p95(400_000.0), abs=1), (
        comparison["latency_p95_delta_ms"]
    )


def test_the_gates_still_read_the_variant_after_the_blanking(tmp_path: Path) -> None:
    """Blanking movement must not turn the nightly door into rubber.

    The gates threshold the *variant*'s own metrics (`_gate_actual`), which this batch
    does not touch: a self-compare still exits 1 on a violated floor and 0 on a kept one.
    """
    one = _write(tmp_path, "nightly-v2.json", _report())
    code_red, comparison = _run(tmp_path, one, one, "--gate", "latency_p95_ms<=1")
    assert code_red == 1, comparison["gates"]
    assert [g["violated"] for g in comparison["gates"]] == [True]
    assert comparison["gates"][0]["actual"] == pytest.approx(_hand_p95(826_000.0), abs=1)
    # A floor the variant does satisfy must still close the door.  (The nightly's own
    # floor, 600000, is *not* satisfied by this 826s-baseline reading - that is the
    # declared-standard-vs-executed-standard gap, and it is the next batch's door.)
    kept = f"latency_p95_ms<={_hand_p95(826_000.0):.0f}"
    code_green, satisfied = _run(tmp_path, one, one, "--gate", kept)
    assert code_green == 0, (kept, satisfied["gates"])
    assert [g["violated"] for g in satisfied["gates"]] == [False]


def test_a_library_caller_that_says_nothing_publishes_an_unknown() -> None:
    """Not told is not evidence of difference - the field must read unknown, not ``False``."""
    report = _report()
    comparison = compare_reports(report, json.loads(json.dumps(report)), repeat=2)
    assert comparison["same_measurement"] is None, (
        f"调用方没有告知两侧的关系，判决却给了一个是/否：{comparison['same_measurement']!r}"
    )


def test_no_relative_gate_ships_while_the_nightly_step_compares_one_file_with_itself() -> None:
    """The two facts the next batch must change *together*.

    A relative line (``..._delta...``) gated against a run compared with itself can only
    ever read "no degradation" - it would certify the very placeholder this batch names.
    Green today because no delta metric is gateable at all; green when both move; red if
    a delta gate arrives while the nightly still hands one file to both sides.
    """
    text = CI.read_bytes().decode("utf-8").replace("\r\n", "\n")
    self_compare = "output/nightly-v2.json --variant output/nightly-v2.json" in text.replace("\n", " ")
    delta_metrics = sorted(metric for metric in bench_compare.GATE_METRICS if "delta" in metric)
    assert not (self_compare and delta_metrics), (
        f"nightly 还在把同一个文件放在两边，却已经给了差值门 {delta_metrics}——"
        "一条相对劣化线在自比下恒读「没有劣化」"
    )
