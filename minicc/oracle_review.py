"""Live code review — the model as senior reviewer of this repository's own diff.

On-duty use of the lane: the model reads the latest commit's actual diff and writes a
short bilingual review of exactly those changes — what is correct, what is risky,
what to verify next. The model never sees anything but the measured diff and the
repo's own counters, and the panel presents its answer as analysis, not as proof.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .oracle_common import call_model, cached_zh_en, error_payload, memo_read, memo_write

_CACHE_KEY = "oracle-review:v1"

_DIFF_STAT_BUDGET = 4000
_DIFF_BODY_BUDGET = 30000


def _git(*args: str, cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=20,
        check=False,
    )
    return out.stdout.decode("utf-8", errors="replace")


def _snapshot(workspace: Path) -> dict[str, Any]:
    root = workspace.resolve()
    head = _git("rev-parse", "--short", "HEAD", cwd=root).strip()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=root).strip()
    parent = _git("rev-list", "--count", "HEAD", cwd=root).strip()
    stat = _git("diff", "HEAD~1..HEAD", "--stat", cwd=root)
    stat = stat[:_DIFF_STAT_BUDGET]
    body = _git("diff", "HEAD~1..HEAD", cwd=root)
    body_trunc = body[:_DIFF_BODY_BUDGET]
    files = [line.split("|", 1)[0].strip() for line in stat.splitlines()[:-1] if "|" in line]
    return {
        "head_short": head,
        "branch": branch,
        "commit_count": parent,
        "files_changed": files,
        "stat": stat,
        "diff": body_trunc,
        "diff_truncated": len(body) > len(body_trunc),
        "diff_bytes": len(body),
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(
        {
            "head_short": snapshot["head_short"],
            "branch": snapshot["branch"],
            "commit_count": snapshot["commit_count"],
            "files_changed": snapshot["files_changed"],
            "stat": snapshot["stat"],
            "diff_truncated": snapshot["diff_truncated"],
        },
        ensure_ascii=False, separators=(",", ":"))
    diff = snapshot["diff"]
    return (
        "你是这台仓库本地优先编程工作台 minicc 的评审值守。下面是仓库 `git diff HEAD~1..HEAD` 的实况——"
        "你是唯一能看见它的人。请写一份代码评审（中文 ≤5 句、英文 ≤5 句）：\n"
        "① 这个提交改了什么（≤2 句，越具体越好）；\n"
        "② 最大的风险或最值得复核的一点（1 句，引用一个具体文件名/行）；\n"
        "③ 修正建议——要么写明‘无需修改 + 理由’，要么指出一个具体改动。\n"
        "纪律：只评这个 diff；不引用 diff 之外的事实；没看到的事实就说没看到。\n"
        "只返回 JSON：{\"zh\": \"…\", \"en\": \"…\"}\n\n"
        f"快照元数据：{body}\n\n"
        f"diff（可能截断，`diff_truncated={str(snapshot['diff_truncated']).lower()}`）：\n```\n{diff}\n```"
    )


def build_workspace_review(*, config: Any | None = None, workspace: Path | None = None,
                           force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written code review; memoized unless force_refresh."""
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    root = Path(workspace) if workspace is not None else Path.cwd()
    if config is None:
        try:
            from .config import load_config

            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return error_payload("config-unavailable", exc)

    try:
        snapshot = _snapshot(root)
    except Exception as exc:  # noqa: BLE001 - an unreadable git tree is reported, not raised
        return error_payload("diff-unavailable", exc)

    try:
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=500, temperature=0.15)
        review = cached_zh_en(call["text"])
        payload = {
            "live": True,
            "zh": review["zh"],
            "en": review["en"],
            "model": call["model"],
            "usage": call["usage"],
            "head_short": snapshot["head_short"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc)
