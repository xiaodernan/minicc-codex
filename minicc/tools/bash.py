"""Bash command runner with timeout, output truncation and risk awareness.

Security model: every command runs in a subprocess, cwd is the workspace.
No sandbox (unlike specproof's Docker DooD) — this is a local-only CLI tool.
The REPL's permission gate (yolo vs confirm) is the only protection layer;
the handler itself just runs and truncates.
"""

from __future__ import annotations

import subprocess
import locale
import os
import signal
import threading
import time
from pathlib import Path

from .registry import split_output
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


def _process_group_kwargs() -> dict[str, int | bool]:
    """Put a shell command in its own group so cancellation reaches children."""
    if os.name == "nt":
        return {"creationflags": int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))}
    return {"start_new_session": True}


def terminate_process_tree(proc: subprocess.Popen[bytes]) -> None:
    """Best-effort termination of a command and every child it spawned."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # ``proc`` is normally cmd.exe; proc.kill() alone would leave a
            # python/node child holding the output pipe open.
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
    except (OSError, subprocess.TimeoutExpired):
        pass

    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass


def _collect_after_termination(proc: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    """Drain pipes after a forced stop without allowing a second hang."""
    terminate_process_tree(proc)
    try:
        stdout, stderr = proc.communicate(timeout=3)
        return stdout or b"", stderr or b""
    except subprocess.TimeoutExpired as exc:
        terminate_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=1)
            return stdout or b"", stderr or b""
        except (OSError, subprocess.TimeoutExpired):
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    try:
                        pipe.close()
                    except OSError:
                        pass
            return bytes(exc.output or b""), bytes(exc.stderr or b"")


def run_process(
    command: str | list[str],
    workspace: Path,
    *,
    timeout: float,
    cancel_event: threading.Event | None = None,
    shell: bool = False,
    env: dict[str, str] | None = None,
    summary_label: str = "命令",
    security_tags: list[str] | None = None,
) -> ToolResult:
    """Run a process while polling for cancellation and bounded timeout."""
    if cancel_event is not None and cancel_event.is_set():
        return ToolResult(
            status="cancelled",
            summary=f"[CANCELLED] {summary_label}已取消，未启动进程",
            security_tags=[*(security_tags or []), "runtime_guard"],
        )

    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            command,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            cwd=str(workspace),
            env=env,
            **_process_group_kwargs(),
        )
    except OSError as exc:
        return ToolResult(
            status="error",
            summary=f"[TOOL_ERROR] 无法执行命令: {exc}",
            duration=round(time.monotonic() - started, 3),
            security_tags=[*(security_tags or []), "untrusted"],
        )

    outcome: str | None = None
    stdout = b""
    stderr = b""
    deadline = started + max(0.01, float(timeout))
    while True:
        if cancel_event is not None and cancel_event.is_set():
            outcome = "cancelled"
            stdout, stderr = _collect_after_termination(proc)
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outcome = "timed_out"
            stdout, stderr = _collect_after_termination(proc)
            break
        try:
            # communicate() drains both pipes, while the short timeout lets
            # the task cancellation event be observed without a pipe deadlock.
            stdout, stderr = proc.communicate(timeout=min(0.2, remaining))
            break
        except subprocess.TimeoutExpired:
            continue

    duration = time.monotonic() - started
    stdout_text = decode_process_output(stdout)
    stderr_text = decode_process_output(stderr)
    output = stdout_text
    if stderr_text and stderr_text.strip():
        output = output + ("\n" if output else "") + f"[stderr]\n{stderr_text}"
    head, tail, truncated = split_output(output)
    tags = list(security_tags or [])
    if not tags:
        tags.append("untrusted")

    if outcome == "cancelled":
        status = "cancelled"
        summary = f"[CANCELLED] {summary_label}已取消并终止进程树 ({duration:.1f}s)"
        tags.append("runtime_guard")
    elif outcome == "timed_out":
        status = "timed_out"
        summary = f"[TIMED_OUT] {summary_label}超时 ({timeout}s)，已终止进程树"
        tags.append("runtime_guard")
    elif proc.returncode == 0:
        status = "ok"
        summary = f"(exit 0, {duration:.1f}s)"
    else:
        status = "error"
        summary = f"[exit {proc.returncode}] ({summary_label}失败, {duration:.1f}s)"

    return ToolResult(
        status=status,
        summary=summary,
        head=head,
        tail=tail,
        truncated=truncated,
        exit_code=proc.returncode,
        duration=round(duration, 3),
        security_tags=tags,
    )


def run_bash(
    command: str,
    workspace: Path,
    timeout: int = DEFAULT_TIMEOUT,
    cancel_event: threading.Event | None = None,
) -> ToolResult:
    """Execute a shell command in the workspace directory."""
    if not command or not command.strip():
        return ToolResult(status="error", summary="[INVALID_ARGUMENTS] command 不能为空")
    return run_process(
        command,
        workspace,
        timeout=timeout,
        cancel_event=cancel_event,
        shell=True,
        env=dict(os.environ),
        summary_label="命令",
        security_tags=["untrusted"],
    )
