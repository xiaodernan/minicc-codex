"""Bash command runner with timeout, output truncation and risk awareness.

Security model: every command runs in a subprocess, cwd is the workspace.
No sandbox (unlike specproof's Docker DooD) — this is a local-only CLI tool.
The REPL's permission gate (yolo vs confirm) is the only protection layer;
the handler itself just runs and truncates.
"""

from __future__ import annotations

import shlex
import subprocess
import locale
import os
import re
import signal
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import split_output
from .schemas import ToolResult

DEFAULT_TIMEOUT = 120
MAX_OUTPUT_CHARS = 32_000
MAX_CAPTURE_BYTES = 256_000
# M6-T4: background shells are tracked in a process-wide registry. Retained
# output per shell is capped (a ring buffer), only a bounded number run at once,
# and a bounded number of finished shells stay pollable before being pruned.
MAX_CONCURRENT_BACKGROUND = 8
MAX_RETAINED_BG_BYTES = 512_000
MAX_FINISHED_SHELLS_KEPT = 16

_DETACHED_COMMAND_RE = re.compile(
    r"(?ix)"
    r"(?:\bstart(?:\.exe)?\b|\bstart-process\b|\bstart-job\b|"
    r"\bnohup\b|\bsetsid\b|\bdisown\b|\bpythonw(?:\.exe)?\b|"
    r"\bnodew(?:\.exe)?\b)"
)


def _has_unquoted_background_operator(command: str) -> bool:
    """Reject a standalone shell '&'; '&&' and '2>&1' remain valid."""
    quote: str | None = None
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "^" and os.name == "nt":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if quote is not None or char != "&":
            continue
        previous = command[index - 1] if index else ""
        following = command[index + 1] if index + 1 < len(command) else ""
        if previous == ">" or following == ">" or previous == "&" or following == "&":
            continue
        return True
    return False


def detached_command_reason(command: str) -> str | None:
    """Return a stable runtime-guard reason for commands that outlive a tool."""
    if _DETACHED_COMMAND_RE.search(command) is not None:
        return "检测到 start/nohup/setsid 等脱离工具生命周期的后台启动"
    if _has_unquoted_background_operator(command):
        return "检测到单独的 shell 后台/链式 '&'，请改用前台命令或 '&&'"
    return None


def _tokenize_segment(segment: str) -> list[str]:
    """Split one operator-free segment into argv tokens.

    Non-posix shlex keeps Windows backslashes literal and preserves quoted
    runs as single tokens; quotes are stripped afterwards. Unbalanced quotes
    degrade to whitespace splitting — callers only inspect token text.
    """
    try:
        lexer = shlex.shlex(segment, posix=False)
        lexer.whitespace_split = True
        lexer.commenters = ""
        raw = list(lexer)
    except ValueError:
        raw = segment.split()
    tokens: list[str] = []
    for token in raw:
        cleaned = token.strip()
        while (
            len(cleaned) >= 2
            and cleaned[0] == cleaned[-1]
            and cleaned[0] in {"'", '"'}
        ):
            cleaned = cleaned[1:-1]
        if cleaned:
            tokens.append(cleaned)
    return tokens


def split_command_argv(command: str) -> list[list[str]]:
    """Shared argv tokenizer (M3-T4 / appendix A.3-3).

    Splits a shell command line at unquoted operators (``&&``, ``||``,
    ``;``, ``|``, ``&``, newlines) and tokenizes each segment. Used by both
    the readonly-pytest gate and the network gate so there is exactly one
    tokenizer in the codebase. The result is for inspection only — never
    execute it.
    """
    text = str(command or "")
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue
        if char in "&|;\n\r":
            if index + 1 < len(text) and text[index + 1] == char:
                index += 1
            segments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    argv_segments = []
    for segment in segments:
        tokens = _tokenize_segment(segment)
        if tokens:
            argv_segments.append(tokens)
    return argv_segments


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
    """Allow only a narrow pytest verification invocation in Web safe mode.

    M2-T5: previously ``argv[0]==pytest`` returned True for *any* flags, so
    ``pytest -p <module>`` (arbitrary code execution) and ``-c <ini>`` /
    ``--rootdir`` / out-of-workspace paths were auto-approved. Now only
    bare ``pytest [paths] [safe flags]`` with in-workspace-relative,
    option-looking-safe arguments passes.
    """
    if not command or any(marker in command for marker in "&|;<>`$()%^!\n\r"):
        return False
    segments = split_command_argv(command)
    if len(segments) != 1:
        return False
    parts = segments[0]
    if not parts:
        return False

    def basename(value: str) -> str:
        return value.strip('"').replace("/", "\\").rsplit("\\", 1)[-1].lower()

    executable = basename(parts[0])
    rest = parts[1:]
    if executable in {"pytest", "pytest.exe"}:
        pass
    elif len(parts) >= 3 and parts[1].lower() == "-m" and parts[2].lower() == "pytest":
        if executable not in {
            "python",
            "python.exe",
            "python3",
            "python3.exe",
            "py",
            "py.exe",
        }:
            return False
        rest = parts[3:]
    else:
        return False

    # Flags that load arbitrary code/config or escape the workspace.
    deny_prefix = ("--rootdir=", "--rootdir:", "--config=", "-c=", "--config:",
                   "--basetemp=", "--basetemp:", "--cache-dir=", "--cache-dir:",
                   "--junitxml=", "--junitxml:", "--resultlog=", "--resultlog:",
                   "--import-mode=", "-o", "--override-ini")
    deny_standalone = {
        "--pyargs", "--rootdir", "--config", "--basetemp", "--cache-dir",
        "--junitxml", "--resultlog", "--override-ini",
    }
    allow_flag_prefix = ("-q", "-x", "-k", "--tb", "-v", "--maxfail", "-m", "--lf", "--ff")
    allow_flag_exact = {
        "--collect-only", "--dry-run", "-s", "--capture=no",
        "--tb=short", "--tb=line", "--tb=native",
    }
    index = 0
    while index < len(rest):
        stripped = rest[index].strip('"')
        lowered = stripped.lower()
        # ``-p`` semantics: ``-p no:<plugin>`` and ``-pno:<plugin>`` only
        # UNLOAD a plugin (safe, used by CI). Any other ``-p<module>`` form
        # LOADS arbitrary code -> deny.
        if lowered == "-p":
            if index + 1 < len(rest) and rest[index + 1].strip('"').lower().startswith("no:"):
                index += 2
                continue
            return False
        if lowered.startswith("-p"):
            if lowered.startswith("-pno:"):
                index += 1
                continue
            return False
        if lowered in deny_standalone:
            return False
        if any(lowered == prefix.rstrip("=") or lowered.startswith(prefix) for prefix in deny_prefix):
            return False
        if stripped.startswith("-"):
            if lowered in allow_flag_exact or lowered.startswith(allow_flag_prefix):
                index += 1
                continue
            return False
        # Positional path args must stay inside the workspace: allow only
        # relative paths without parent segments or drive/UNC/absolute forms.
        if stripped in {".", "./", "./tests", "tests", "tests/"}:
            index += 1
            continue
        norm = stripped.replace("\\", "/")
        if (
            norm.startswith("/")
            or ":\\" in stripped
            or stripped.startswith("\\\\")
            or (len(stripped) > 1 and stripped[1] == ":")
            or norm.startswith("../")
            or "/../" in norm
            or norm == ".."
        ):
            return False
        if ".." in norm.split("/"):
            return False
        index += 1
    return True


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
            # M4-7 follow-up: do NOT close the pipes here. A parked reader makes
            # ``close()`` wait for the in-flight read to finish (see
            # run_process), which is how a detached child used to stall this
            # path for its whole lifetime. The daemon readers own the handles and
            # release them when the write end finally closes.
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
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    output_lock = threading.Lock()
    output_overflow = {"stdout": False, "stderr": False}

    def drain(pipe: Any, chunks: list[bytes], stream_name: str) -> None:
        """Drain independently so inherited child handles cannot block the worker."""
        captured = 0
        try:
            while True:
                reader = getattr(pipe, "read1", None)
                chunk = reader(8192) if callable(reader) else pipe.read(8192)
                if not chunk:
                    return
                with output_lock:
                    remaining = MAX_CAPTURE_BYTES - captured
                    if remaining > 0:
                        chunks.append(bytes(chunk[:remaining]))
                        captured += min(len(chunk), remaining)
                    if len(chunk) > remaining:
                        output_overflow[stream_name] = True
        except (OSError, ValueError):
            return
        finally:
            # This thread owns the read side, so closing here can never wait on
            # an in-flight read. The main thread must not close a pipe while a
            # reader is parked in it (see run_process below).
            try:
                pipe.close()
            except (OSError, ValueError):
                pass

    readers = [
        threading.Thread(target=drain, args=(proc.stdout, stdout_chunks, "stdout"), daemon=True),
        threading.Thread(target=drain, args=(proc.stderr, stderr_chunks, "stderr"), daemon=True),
    ]
    for reader in readers:
        reader.start()

    deadline = started + max(0.01, float(timeout))
    while True:
        if cancel_event is not None and cancel_event.is_set():
            outcome = "cancelled"
            terminate_process_tree(proc)
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outcome = "timed_out"
            terminate_process_tree(proc)
            break
        if proc.poll() is not None:
            break
        # Polling is deliberately independent from pipe draining. A child that
        # inherits stdout/stderr can keep EOF open after the shell exits, but it
        # must never keep this tool worker blocked on communicate().
        time.sleep(min(0.1, remaining))

    if outcome is None:
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            outcome = "timed_out"
            terminate_process_tree(proc)

    # Close the parent read handles after a bounded drain. Reader threads are
    # daemonized as a final defense against a detached child retaining a pipe.
    for reader in readers:
        reader.join(timeout=0.25)
    # M4-7 follow-up: never close a pipe whose reader is still parked in
    # read1(). On Windows ``BufferedReader.close()`` waits for the in-flight
    # read to finish, which silently re-introduced the exact stall this
    # function promises to avoid: measured on a command whose grandchild held
    # the pipe for 20s, the shell exited at 3.7s but ``run_bash`` returned at
    # 22s. Each reader now closes its own pipe when it reaches EOF, so the
    # handle is still released — by the thread that owns the read.
    for pipe, reader in ((proc.stdout, readers[0]), (proc.stderr, readers[1])):
        if pipe is None or reader.is_alive():
            continue
        try:
            pipe.close()
        except OSError:
            pass
    for reader in readers:
        reader.join(timeout=0.25)

    with output_lock:
        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)

    duration = time.monotonic() - started
    stdout_text = decode_process_output(stdout)
    stderr_text = decode_process_output(stderr)
    output = stdout_text
    if stderr_text and stderr_text.strip():
        output = output + ("\n" if output else "") + f"[stderr]\n{stderr_text}"
    head, tail, truncated = split_output(output)
    truncated = truncated or any(output_overflow.values())
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
    run_in_background: bool = False,
) -> ToolResult:
    """Execute a shell command in the workspace directory.

    ``run_in_background`` (M6-T4) is the *supported* way to run a long-lived
    command: it returns a ``shell_id`` immediately, keeps the process in its own
    process group, and streams bounded output into a ring buffer the model polls
    with ``bash_output``. The detached-start guards (``&`` / ``nohup`` /
    ``start`` / ``setsid``) stay rejected for BOTH modes — backgrounding is
    explicit and tracked, not an escape from the tool lifecycle.
    """
    if not command or not command.strip():
        return ToolResult(status="error", summary="[INVALID_ARGUMENTS] command 不能为空")
    detached_reason = detached_command_reason(command)
    if detached_reason:
        return ToolResult(
            status="error",
            summary=f"[RUNTIME_GUARD] {detached_reason}；命令未启动",
            security_tags=["untrusted", "runtime_guard"],
            data={
                "code": "detached_process_blocked",
                "retryable": True,
                "suggestion": (
                    "需要长驻或异步执行请改用 run_in_background=true（随后用 bash_output 轮询、"
                    "kill_shell 终止）；前台命令请直接以前台方式运行。"
                ),
            },
        )
    if run_in_background:
        return start_background_shell(command, workspace)
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


@dataclass
class _BackgroundShell:
    shell_id: str
    command: str
    proc: "subprocess.Popen[bytes]"
    started: float
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    buffer: bytearray = field(default_factory=bytearray, repr=False)
    dropped: int = 0
    cursor: int = 0
    finished: bool = False
    exit_code: int | None = None
    killed: bool = False


_BG_SHELLS: dict[str, _BackgroundShell] = {}
_BG_ORDER: deque[str] = deque()  # insertion order, oldest first
_BG_LOCK = threading.Lock()


def _bg_prune_locked() -> None:
    """Forget the oldest finished shells once too many are retained."""
    finished = [sid for sid in _BG_ORDER if _BG_SHELLS[sid].finished]
    excess = len(finished) - MAX_FINISHED_SHELLS_KEPT
    for sid in finished[:max(0, excess)]:
        _BG_SHELLS.pop(sid, None)
        try:
            _BG_ORDER.remove(sid)
        except ValueError:
            pass


def _bg_running_count_locked() -> int:
    return sum(1 for shell in _BG_SHELLS.values() if not shell.finished)


def _bg_reader(shell: _BackgroundShell) -> None:
    """Drain the merged stdout/stderr pipe into the bounded ring buffer."""
    proc = shell.proc
    try:
        while True:
            pipe = proc.stdout
            if pipe is None:
                break
            reader = getattr(pipe, "read1", None)
            chunk = reader(8192) if callable(reader) else pipe.read(8192)
            if not chunk:
                break
            with shell.lock:
                shell.buffer.extend(chunk)
                overflow = len(shell.buffer) - MAX_RETAINED_BG_BYTES
                if overflow > 0:
                    del shell.buffer[:overflow]
                    shell.dropped += overflow
    except (OSError, ValueError):
        pass
    finally:
        try:
            exit_code = proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            exit_code = proc.poll()
        with shell.lock:
            shell.finished = True
            shell.exit_code = exit_code
        for pipe in (proc.stdout, getattr(proc, "stderr", None)):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass


def start_background_shell(command: str, workspace: Path) -> ToolResult:
    """Launch a tracked, cancellable background shell (M6-T4)."""
    with _BG_LOCK:
        _bg_prune_locked()
        if _bg_running_count_locked() >= MAX_CONCURRENT_BACKGROUND:
            return ToolResult(
                status="error",
                summary=f"[RUNTIME_GUARD] 后台 shell 已达并发上限（{MAX_CONCURRENT_BACKGROUND}）",
                output="请先用 kill_shell 结束不再需要的后台 shell，或等待其退出。",
                data={"code": "background_limit_reached", "retryable": True},
                security_tags=["untrusted", "runtime_guard", "background_shell"],
            )
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                cwd=str(workspace),
                env=dict(os.environ),
                **_process_group_kwargs(),
            )
        except OSError as exc:
            return ToolResult(
                status="error",
                summary=f"[TOOL_ERROR] 无法启动后台命令: {exc}",
                security_tags=["untrusted", "background_shell"],
            )
        shell = _BackgroundShell(
            shell_id=f"bg-{uuid.uuid4().hex[:8]}",
            command=command,
            proc=proc,
            started=time.monotonic(),
        )
        _BG_SHELLS[shell.shell_id] = shell
        _BG_ORDER.append(shell.shell_id)
    threading.Thread(target=_bg_reader, args=(shell,), daemon=True, name=f"minicc-bg-{shell.shell_id}").start()
    return ToolResult(
        status="ok",
        summary=f"已在后台启动 shell {shell.shell_id}",
        output=(
            f"shell_id={shell.shell_id}\n"
            "用 bash_output(shell_id) 增量读取输出，用 kill_shell(shell_id) 终止整个进程树。"
        ),
        data={"shell_id": shell.shell_id, "pid": proc.pid, "background": True},
        security_tags=["untrusted", "background_shell"],
    )


def _bg_shell_or_error(shell_id: str) -> tuple[_BackgroundShell | None, ToolResult | None]:
    with _BG_LOCK:
        shell = _BG_SHELLS.get(str(shell_id))
    if shell is None:
        return None, ToolResult(
            status="error",
            summary=f"[UNKNOWN_SHELL] 找不到后台 shell {shell_id!r}",
            data={"available": _bg_known_ids()},
            security_tags=["untrusted", "background_shell"],
        )
    return shell, None


def _bg_known_ids() -> list[str]:
    with _BG_LOCK:
        return list(_BG_SHELLS)


def poll_background_shell(shell_id: str, *, since_start: bool = False) -> ToolResult:
    """Return new output for a background shell since the last poll."""
    shell, error = _bg_shell_or_error(shell_id)
    if shell is None:
        return error  # type: ignore[return-value]
    assert shell is not None
    with shell.lock:
        if since_start:
            start = shell.dropped
        else:
            start = max(shell.cursor, shell.dropped)
        offset = start - shell.dropped if start >= shell.dropped else 0
        payload = bytes(shell.buffer[offset:])
        shell.cursor = shell.dropped + len(shell.buffer)
        finished = shell.finished
        exit_code = shell.exit_code
        dropped = shell.dropped
    text = decode_process_output(payload)
    status_line = (
        f"状态: 已退出 (exit {exit_code})" if finished else f"状态: 运行中 (pid {shell.proc.pid})"
    )
    dropped_note = f"\n[更早的 {dropped} 字节输出已被环形缓冲丢弃]" if (dropped and since_start) else ""
    body = text if text.strip() else "(暂无新输出)"
    full_text = f"{status_line}\n{body}{dropped_note}"
    head, tail, truncated = split_output(full_text)
    return ToolResult(
        status="ok",
        summary=f"后台 shell {shell.shell_id} 输出" + ("（已结束）" if finished else "（运行中）"),
        head=head,
        tail=tail,
        truncated=truncated or (dropped > 0 and since_start),
        data={
            "shell_id": shell.shell_id,
            "finished": finished,
            "exit_code": exit_code,
            "new_bytes": len(payload),
            "dropped_bytes": dropped,
        },
        security_tags=["untrusted", "background_shell"],
    )


def kill_background_shell(shell_id: str) -> ToolResult:
    """Terminate a background shell's whole process group."""
    shell, error = _bg_shell_or_error(shell_id)
    if shell is None:
        return error  # type: ignore[return-value]
    assert shell is not None
    already = shell.finished
    terminate_process_tree(shell.proc)
    with shell.lock:
        shell.killed = True
        finished = shell.finished
        exit_code = shell.proc.poll()
        if finished:
            shell.exit_code = shell.exit_code
        else:
            shell.finished = True
            shell.exit_code = exit_code
            exit_code = shell.exit_code
    return ToolResult(
        status="ok",
        summary=(
            f"后台 shell {shell.shell_id} 已结束"
            if already else f"已终止后台 shell {shell.shell_id} 的进程树"
        ),
        data={"shell_id": shell.shell_id, "exit_code": exit_code, "was_running": not already},
        output=f"shell {shell.shell_id} 进程树已终止，pid {shell.proc.pid} poll={shell.proc.poll()}",
        security_tags=["untrusted", "runtime_guard", "background_shell"],
    )
