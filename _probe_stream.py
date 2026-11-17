# -*- coding: utf-8 -*-
"""Stream probe with the NEW key."""
import os
import json
import time
from pathlib import Path

for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip()

import httpx

base = os.environ["MINICC_BASE_URL"].rstrip("/")
model = os.environ["MINICC_MODEL"]
key = os.environ["MINICC_API_KEY"]

payload = {
    "model": model,
    "stream": True,
    "stream_options": {"include_usage": True},
    "temperature": 0,
    "max_tokens": 80,
    "prompt_cache_key": "minicc-newkey-probe-01",
    "messages": [
        {"role": "system", "content": "You are a careful code auditor. Answer in the user's language."},
        {"role": "user", "content": "你是一个代码审计员。这段 git diff 里引入了哪些语义变化？用一段话作答。\n\ndiff sample: minicc/clock.py adds utc_stamp(ts=None) -> strftime('%Y-%m-%dT%H:%M:%SZ', gmtime(ts))"},
    ],
}

for attempt in (1, 2):
    t0 = time.time()
    with httpx.stream("POST", f"{base}/chat/completions",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json=payload, timeout=90) as r:
        chars = 0
        cached = None
        prompt_tokens = None
        completion_tokens = None
        for line in r.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            usage = obj.get("usage") or {}
            if usage.get("prompt_tokens"):
                prompt_tokens = usage["prompt_tokens"]
                completion_tokens = usage.get("completion_tokens")
                cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                continue
            chs = obj.get("choices") or []
            if not chs:
                continue
            delta = chs[0].get("delta") or {}
            if delta.get("content"):
                chars += len(delta["content"])
        if cached is None:
            cached = "usage chunk not seen"
        dt = time.time() - t0
        print(f"stream #{attempt}: status={r.status_code} chars={chars} prompt={prompt_tokens} completion={completion_tokens} cached={cached} wall={dt:.1f}s")
