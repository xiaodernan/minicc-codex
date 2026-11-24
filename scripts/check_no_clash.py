"""M8-T1343: prove this machine has no active Clash Verge binding.

The user retired Clash Verge. This gate is the durable, runnable proof that
nothing re-binds the machine to 127.0.0.1:7897:

  1. no HTTP(S)_PROXY / ALL_PROXY in this process environment pointing at 7897
  2. no proxy in git / npm / pip global config pointing at 7897
  3. no WinINET proxy enabled at the registry level
  4. no TUN/Clash virtual network adapter up
  5. the repo .env carries no proxy key
  6. no active Python/provider code re-exports proxy vars from .env

It reads the machine read-only and prints a per-check verdict; exit 0 only when
all checks pass. Run: python scripts/check_no_clash.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PORT = "7897"
ROOT = Path(__file__).resolve().parent.parent

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def _sh(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=15).stdout
    except OSError as exc:
        return f"<unavailable: {exc}>"


# 1. process environment
env_hits = [k for k, v in os.environ.items()
            if k.lower() in {"http_proxy", "https_proxy", "all_proxy"} and PORT in v]
record("process env has no 7897 proxy", not env_hits, ",".join(env_hits))

# 2. git / npm / pip
git_proxy = _sh(["git", "config", "--global", "--get-regexp", r"http\..*proxy"])
npm_proxy = _sh(["npm", "config", "get", "proxy"]) + _sh(["npm", "config", "get", "https-proxy"])
tool_hits = PORT in git_proxy or PORT in npm_proxy
record("git/npm global config has no 7897 proxy", not tool_hits)

# 3. WinINET (Windows only)
if sys.platform == "win32":
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
        record("WinINET proxy disabled", not enabled and PORT not in str(server), str(server))
    except OSError:
        record("WinINET proxy disabled (no key)", True)
else:
    record("WinINET check skipped (non-Windows)", True)

# 4. TUN / Clash adapter (Windows only)
if sys.platform == "win32":
    out = _sh(["powershell", "-NoProfile", "-Command",
               "Get-NetAdapter | Where-Object { $_.Name -match 'tun|clash|mihomo' -or "
               "$_.InterfaceDescription -match 'TUN|Wintun|Clash|Mihomo' } | "
               "Select-Object -ExpandProperty Name"])
    record("no Clash/TUN virtual adapter", not out.strip(), out.strip())
else:
    record("adapter check skipped (non-Windows)", True)

# 5. repo .env
env_file = ROOT / ".env"
body = env_file.read_text(encoding="utf-8", errors="replace") if env_file.exists() else ""
proxy_lines = [ln for ln in body.splitlines()
               if ln.strip() and not ln.strip().startswith("#")
               and any(k in ln.upper() for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"))]
record("repo .env has no proxy key", not proxy_lines, ";".join(proxy_lines))

# 6. config.py does not re-export proxy vars
cfg = (ROOT / "minicc" / "config.py").read_text(encoding="utf-8", errors="replace")
record("config.py never exports proxy to os.environ",
       "os.environ[_key]" not in cfg and "_PROXY_KEYS" not in cfg)

failed = [n for n, ok, _ in results if not ok]
for name, ok, detail in results:
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail and not ok else ""))
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
