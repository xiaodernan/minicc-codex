"""Live wkapi.pro cache-affinity measurement probe — the same methodology that
fills docs/CACHE_AFFINITY_MATRIX.md, runnable on demand.

Reads the OpenAI-compatible gateway settings from the process environment
(MINICC_API_KEY / MINICC_BASE_URL / MINICC_MODEL) with an optional fallback to a
gitignored repo-local .env file. NOTHING from either source is printed, logged,
or committed — output contains token counts and ratios only. One lane key is
deliberately fresh-per-day (minicc-measurement-YYYY-MM-DD-a) so cold-vs-warm is
always read from data, never from memory.

Usage:
    .venv\\Scripts\\python.exe scripts\\measure_cache_affinity.py            # live, ~17k prompt tokens
    .venv\\Scripts\\python.exe scripts\\measure_cache_affinity.py --dry-run # shape-only, zero network

Band reference (docs/CACHE_AFFINITY_MATRIX.md): warm Responses streaming hits
land at ~94–100 % for a ~5.5k-token stable prefix; first call on a fresh lane
key reads ~74 % cold.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

LANE = "minicc-measurement-2026-11-16-a"
RULE = (
    "你是一个在代码仓库里工作的智能体。先观察，后动手。"
    "每次变更必须最小：只改必须改的文件，不引入多余依赖，不改变未要求的行为。"
    "回答中如果涉及数字，必须是从仓库或接口读到的真实数字，不得估算，不得捏造。"
    "不确定时先问；拿不准时停下来；完成的定义是全部验证通过。"
)
STABLE_PREFIX = "\n".join([RULE] * 14)
ASKS = [
    "（问 A）用三个词概括你的工作原则。",
    "（问 A 精确复读）用三个词概括你的工作原则。",
    "（问 B）再用两个词补充一个前面没有提到的原则。",
]


def _load_settings() -> tuple[str | None, str, str]:
    key = os.environ.get("MINICC_API_KEY")
    base = os.environ.get("MINICC_BASE_URL")
    model = os.environ.get("MINICC_MODEL")
    if key:
        return key, base or "https://wkapi.pro/v1", model or "gpt-6-sol"
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == "MINICC_API_KEY" and v.strip():
                key = v.strip()
            elif k.strip() == "MINICC_BASE_URL" and v.strip():
                base = v.strip()
            elif k.strip() == "MINICC_MODEL" and v.strip():
                model = v.strip()
    return key, base or "https://wkapi.pro/v1", model or "gpt-6-sol"


def main() -> int:
    dry = "--dry-run" in sys.argv
    key, base, model = _load_settings()
    if dry:
        print(f"dry-run: lane={LANE} prefix_lines={STABLE_PREFIX.count(chr(10))+1} asks={len(ASKS)}")
        print("dry-run: would open https://<gateway>/v1 with 3 streaming Responses calls; key never printed")
        return 0
    if not key:
        print("NO_KEY: set MINICC_API_KEY or a gitignored .env first", flush=True)
        return 2

    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=base)
    for i, q in enumerate(ASKS, 1):
        try:
            stream = client.responses.create(
                model=model,
                input=STABLE_PREFIX + "\n" + q,
                max_output_tokens=48,
                stream=True,
                prompt_cache_key=LANE,
                store=False,
            )
            usage = None
            for event in stream:
                if getattr(event, "type", None) == "response.completed":
                    usage = getattr(getattr(event, "response", None), "usage", None)
            if usage is None:
                print(f"req {i}: usage missing", flush=True)
                continue
            details = getattr(usage, "input_tokens_details", None)
            cached = getattr(details, "cached_tokens", None) if details is not None else None
            ptok = getattr(usage, "input_tokens", None) or 0
            if isinstance(cached, int) and ptok:
                print(f"req {i}: input={ptok} cached={cached} pct={100 * cached / ptok:.1f}%", flush=True)
            else:
                print(f"req {i}: input={ptok} cached={cached}", flush=True)
        except Exception as exc:  # noqa: BLE001 - stability of the probe matters more than type precision in print
            print(f"req {i}: ERROR {type(exc).__name__}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
