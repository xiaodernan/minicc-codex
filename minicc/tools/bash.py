"""Bash command runner with timeout, output truncation and risk awareness.

Security model: every command runs in a subprocess, cwd is the workspace.
No sandbox (unlike specproof's Docker DooD) — this is a local-only CLI tool.
The REPL's permission gate (yolo vs confirm) is the only protection layer;
the handler itself just runs and truncates.
"""

from __future__ import annotations

import subprocess
import sys
import time
import locale
from pathlib import Path
from typing import Any

from .registry import ToolError, split_output
from .schemas import ToolResult

DEFAULT_TIMEOUT = 120
MAX_OUTPUT_CHARS = 32_000


def decode_process_output(value: bytes | str | None) -> str:
    """Decode command output without crashing on a Windows code page."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raw = bytes(value)
    if not raw:
        return ""
    encodings = ["utf-8", "gb18030", "cp936", locale.getpreferredencoding(False)]
    for encoding in dict.fromkeys(item for item in encodings if item):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def is_readonly_command(command: str) -> bool:
    """Allow only a simple pytest invocation in Web safe mode.

    Tests are still code execution, so this is deliberately narrow: shell
    composition, redirection, and other interpreters remain blocked.
    """
    if not command or any(marker in command for marker in "&|;<>`$()%^!\n\r"):
        return False
    parts = command.strip().split()
    if not parts:
        return False

    def basename(value: str) -> str:
        return value.strip('"').replace("/", "\\").rsplit("\\", 1)[-1].lower()

    executable = basename(parts[0])
    if executable in {"pytest", "pytest.exe"}:
        return True
    if len(parts) >= 3 and parts[1].lower() == "-m" and parts[2].lower() == "pytest":
        return executable in {
            "python",
            "python.exe",
            "python3",
            "python3.exe",
            "py",
            "py.exe",
        }
    return False


def run_bash(
    command: str,
    workspace: Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> ToolResult:
    """Execute a shell command in the workspace directory."""
    if not command or not command.strip():
        return ToolResult(status="error", summary="[INVALID_ARGUMENTS] command 不能为空")

    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=False,
            timeout=timeout,
            cwd=str(workspace),
            env={**__import__("os").environ},
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        return ToolResult(
            status="timed_out",
            summary=f"[TIMED_OUT] 命令超时 ({timeout}s)",
            duration=round(elapsed, 3),
        )
    except OSError as exc:
        return ToolResult(
            status="error",
            summary=f"[TOOL_ERROR] 无法执行命令: {exc}",
            duration=round(time.monotonic() - started, 3),
        )

    duration = time.monotonic() - started
    stdout = decode_process_output(proc.stdout)
    stderr = decode_process_output(proc.stderr)
    output = stdout
    if stderr and stderr.strip():
        output = output + ("\n" if output else "") + f"[stderr]\n{stderr}"
    head, tail, truncated = split_output(output)

    if proc.returncode == 0:
        status = "ok"
        summary = f"(exit 0, {duration:.1f}s)"
    else:
        status = "error"
        summary = f"[exit {proc.returncode}] (命令失败, {duration:.1f}s)"

    return ToolResult(
        status=status,
        summary=summary,
        head=head,
        tail=tail,
        truncated=truncated,
        exit_code=proc.returncode,
        duration=round(duration, 3),
        security_tags=["untrusted"],
    )
