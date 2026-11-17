# -*- coding: utf-8 -*-
"""Real API probe with the NEW key: non-stream vs stream, measured cache tokens."""
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

PROMPT = "你是一个代码审计员。这段 git diff 里引入了哪些语义变化？用一段话作答。"
DIFF = "diff sample: minicc/clock.py adds utc_stamp(ts=None) -> strftime('%Y-%m-%dT%H:%M:%SZ', gmtime(ts))"

def payload(stream: bool):
    return {
        "model": model,
        "stream": stream,
        "temperature": 0,
        "max_tokens": 80,
        "prompt_cache_key": "minicc-newkey-probe-01",
        "messages": [
            {"role": "system", "content": "You are a careful code auditor. Answer in the user's language."},
            {"role": "user", "content": f"{PROMPT}\n\n{DIFF}"},
        ],
    }

def nonstream():
    r = httpx.post(f"{base}/chat/completions",
                   headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   json=payload(False), timeout=90)
    d = r.json()
    usage = d.get("usage") or {}
    print("non-stream:", r.status_code, "usage:", json.dumps(usage, ensure_ascii=False))

def stream():
    t0 = time.time()
    with httpx.stream("POST", f"{base}/chat/completions",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json=payload(True), timeout=90) as r:
        chars = 0
        cached = None
        prompt_tokens = None
        for line in r.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            obj = json.loads(data)
            deltas = obj.get("choices", [{}])[0].get("delta", {})
            if deltas.get("content"):
                chars += len(deltas["content"])
            if (obj.get("usage") or {}).get("prompt_tokens"):
                prompt_tokens = obj["usage"]["prompt_tokens"]
                cached = (obj["usage"].get("prompt_tokens_details") or {}).get("cached_tokens")
        dt = time.time() - t0
        print(f"stream: {r.status_code} chars={chars} prompt={prompt_tokens} cached={cached} wall={dt:.1f}s")

print("== non-stream (twice: first may be cold) ==")
nonstream()
nonstream()
print("== stream (twice) ==")
stream()
stream()
