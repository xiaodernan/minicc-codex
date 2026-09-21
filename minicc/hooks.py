"""M7-T1: user-configured hooks for agent lifecycle events.

Four events, mirroring the Claude Code hook contract:

* ``PreToolUse``      — before a tool executes; may *deny* the call.
* ``PostToolUse``     — after a tool returned; audit only.
* ``UserPromptSubmit``— before a user prompt enters the agent loop; may block.
* ``Stop``            — after the agent finished; audit only.

Configuration lives in ``<workspace>/.minicc/hooks.json`` (off by default):

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "bash|write_file", "command": "python check.py",
       "timeout": 5, "on_failure": "continue", "env": {}}
    ]
  }
}
```

Security contract (mirrors the platform rules the roadmap demands):

* The hook command is *user* configuration — it runs with the user's own
  privileges, ``cwd`` pinned to the workspace, and a **scrubbed environment**
  (PATH + OS essentials + the entry's explicit ``env``). The parent's
  ``MINICC_API_KEY`` / web bearer token never leak into hook processes.
* ``.minicc/hooks.json`` itself is in the sensitive-file set (M2-T2): the
  agent cannot write it, so an agent can never install a hook.
* Hook stdout/stderr are **untrusted data**: redacted and capped before they
  may enter any conversation or trace.
* A ``PreToolUse`` hook may only *deny*. It can never allow what
  ``authorize_tool`` already refused — permission boundaries are not
  overridable by hooks (roadmap M7-T1 acceptance).
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .tools.registry import redact_text

HOOK_EVENTS = ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop")
DEFAULT_HOOK_TIMEOUT = 5.0
MAX_HOOK_OUTPUT_CHARS = 2000
HOOKS_FILENAME = "hooks.json"
# Exit code a hook uses to explicitly deny/block (2 mirrors git hook style).
HOOK_DENY_EXIT = 2

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class HookConfigError(RuntimeError):
    """hooks.json is malformed; the hook system stays disabled."""


@dataclass
class HookSpec:
    event: str
    command: str
    matcher: str = ""  # regex against the tool name (tool events only)
    timeout: float = DEFAULT_HOOK_TIMEOUT
    on_failure: str = "continue"  # continue | deny
    env: dict[str, str] = field(default_factory=dict)

    def matches_tool(self, tool: str) -> bool:
        if not self.matcher:
            return True
        try:
            return re.search(self.matcher, tool) is not None
        except re.error:
            return False


@dataclass
class HookOutcome:
    """Result of running every hook registered for one event."""

    decision: str = "allow"  # allow | deny
    outputs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def denied(self) -> bool:
        return self.decision == "deny"

    def denial_reason(self) -> str:
        for entry in self.outputs:
            if entry.get("decision") == "deny":
                return str(entry.get("reason") or "hook denied")
        return "hook denied"


def _scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Minimal, allow-listed environment for hook subprocesses."""
    env: dict[str, str] = {}
    for name in ("PATH", "PATH_EXT", "PATHEXT", "SYSTEMROOT", "SystemRoot",
                 "COMSPEC", "ComSpec", "TEMP", "TMP", "HOME", "USERPROFILE",
                 "USERNAME", "LANG", "LC_ALL", "PYTHONIOENCODING"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    for key, value in (extra or {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)):
            raise HookConfigError(f"hook env 键名非法: {key!r}")
        env[str(key)] = str(value)
    return env


def _kill_process_tree(proc: "subprocess.Popen[str]") -> None:
    """Terminate a timed-out hook *and its children* (shell=True spawns)."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()


def _cap(text: str) -> str:
    if len(text) <= MAX_HOOK_OUTPUT_CHARS:
        return text
    head = text[: MAX_HOOK_OUTPUT_CHARS // 2]
    tail = text[-MAX_HOOK_OUTPUT_CHARS // 2 :]
    return f"{head}\n...[hook output truncated]...\n{tail}"


class HookRunner:
    """Loads hooks.json once and executes matching hooks synchronously."""

    def __init__(self, workspace: Path | None, *, config: dict[str, Any] | None = None) -> None:
        self.workspace = Path(workspace).resolve() if workspace else Path.cwd().resolve()
        self.specs: list[HookSpec] = []
        self.load_error: str | None = None
        self._env_lock = threading.Lock()
        if os.getenv("MINICC_HOOKS", "1").strip().lower() in {"0", "false", "off"}:
            return
        if config is None:
            config = self._read_config_file()
        if config is not None:
            try:
                self._parse(config)
            except HookConfigError as exc:
                self.load_error = str(exc)
                self.specs = []

    # -- loading -----------------------------------------------------------

    def _read_config_file(self) -> dict[str, Any] | None:
        path = self.workspace / ".minicc" / HOOKS_FILENAME
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise HookConfigError(f"无法读取 {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise HookConfigError(f"{path} 顶层必须是 JSON 对象")
        return data

    def _parse(self, data: dict[str, Any]) -> None:
        hooks = data.get("hooks", data)
        if not isinstance(hooks, dict):
            raise HookConfigError("hooks 字段必须是对象")
        for event, entries in hooks.items():
            if event not in HOOK_EVENTS:
                raise HookConfigError(f"未知 hook 事件: {event!r} (可用: {list(HOOK_EVENTS)})")
            if not isinstance(entries, list):
                raise HookConfigError(f"hooks.{event} 必须是数组")
            for index, raw in enumerate(entries):
                if not isinstance(raw, dict):
                    raise HookConfigError(f"hooks.{event}[{index}] 必须是对象")
                command = str(raw.get("command") or "").strip()
                if not command:
                    raise HookConfigError(f"hooks.{event}[{index}].command 不能为空")
                matcher = str(raw.get("matcher") or "")
                if matcher:
                    try:
                        re.compile(matcher)
                    except re.error as exc:
                        raise HookConfigError(
                            f"hooks.{event}[{index}].matcher 非法正则: {exc}"
                        ) from exc
                try:
                    timeout = float(raw.get("timeout", DEFAULT_HOOK_TIMEOUT))
                except (TypeError, ValueError) as exc:
                    raise HookConfigError(
                        f"hooks.{event}[{index}].timeout 必须是数字"
                    ) from exc
                if not (0 < timeout <= 60):
                    raise HookConfigError(f"hooks.{event}[{index}].timeout 需在 (0, 60] 秒")
                on_failure = str(raw.get("on_failure", "continue")).strip().lower()
                if on_failure not in {"continue", "deny"}:
                    raise HookConfigError(
                        f"hooks.{event}[{index}].on_failure 非法: {on_failure!r} (continue|deny)"
                    )
                env_raw = raw.get("env") or {}
                if not isinstance(env_raw, dict):
                    raise HookConfigError(f"hooks.{event}[{index}].env 必须是对象")
                self.specs.append(
                    HookSpec(
                        event=event,
                        command=command,
                        matcher=matcher,
                        timeout=timeout,
                        on_failure=on_failure,
                        env={str(k): str(v) for k, v in env_raw.items()},
                    )
                )

    # -- introspection ------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return bool(self.specs)

    def events(self) -> list[str]:
        return sorted({spec.event for spec in self.specs})

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "events": self.events(),
            "count": len(self.specs),
            "load_error": self.load_error,
        }

    # -- execution ----------------------------------------------------------

    def run(self, event: str, payload: dict[str, Any]) -> HookOutcome:
        """Run every hook matching *event*; never raises."""
        outcome = HookOutcome()
        if event not in HOOK_EVENTS:
            return outcome
        tool = str(payload.get("tool") or "")
        for spec in self.specs:
            if spec.event != event:
                continue
            if event in {"PreToolUse", "PostToolUse"} and not spec.matches_tool(tool):
                continue
            entry = self._run_one(spec, payload)
            outcome.outputs.append(entry)
            if entry["decision"] == "deny":
                outcome.decision = "deny"
        return outcome

    def _run_one(self, spec: HookSpec, payload: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "event": spec.event,
            "command": spec.command,
            "decision": "allow",
            "reason": "",
        }
        try:
            env = _scrubbed_env(spec.env)
        except HookConfigError as exc:
            entry.update(decision="error", reason=str(exc))
            return entry
        body = json.dumps(payload, ensure_ascii=False, default=str)
        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            # Own process group so a timeout can SIGKILL the whole tree;
            # killing only the shell would leave grandchildren alive holding
            # the capture pipes, which blocks communicate() past the timeout.
            popen_kwargs["start_new_session"] = True
        try:
            with self._env_lock:  # serialize spawns; hooks may mutate workspace
                proc = subprocess.Popen(  # noqa: S603 - user-configured command
                    spec.command,
                    shell=True,
                    cwd=str(self.workspace),
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **popen_kwargs,
                )
        except OSError as exc:
            entry.update(
                decision="deny" if spec.on_failure == "deny" else "allow",
                reason=f"hook 启动失败: {exc}",
            )
            return entry
        try:
            stdout_raw, stderr_raw = proc.communicate(input=body, timeout=spec.timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            try:
                stdout_raw, stderr_raw = proc.communicate(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_raw, stderr_raw = "", ""
            entry.update(
                decision="deny" if spec.on_failure == "deny" else "allow",
                exit_code=proc.returncode,
                timed_out=True,
                stdout=redact_text(_cap((stdout_raw or "").strip()))[0],
                stderr=redact_text(_cap((stderr_raw or "").strip()))[0],
                reason=f"hook 超时（>{spec.timeout:.0f}s），已连同子进程一起终止",
            )
            return entry
        except OSError as exc:
            _kill_process_tree(proc)
            entry.update(
                decision="deny" if spec.on_failure == "deny" else "allow",
                reason=f"hook 执行失败: {exc}",
            )
            return entry
        stdout, _ = redact_text(_cap((stdout_raw or "").strip()))
        stderr, _ = redact_text(_cap((stderr_raw or "").strip()))
        entry.update(exit_code=proc.returncode, stdout=stdout, stderr=stderr)
        if proc.returncode == 0:
            entry["decision"] = "allow"
        elif proc.returncode == HOOK_DENY_EXIT:
            entry.update(decision="deny", reason=stdout or stderr or "hook denied")
        else:
            # Non-zero, non-deny exit: failure strategy decides.
            entry.update(
                decision="deny" if spec.on_failure == "deny" else "allow",
                reason=(stderr or stdout or f"hook 退出码 {proc.returncode}"),
            )
        return entry


def payloads_for_tool_call(
    event: str, tool: str, arguments: Any, *, risk: str | None = None
) -> dict[str, Any]:
    """Build the (redacted) hook payload for a tool event."""
    safe_args = arguments
    if isinstance(arguments, dict):
        safe_args = {}
        for key, value in arguments.items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
            if isinstance(text, str):
                redacted, _ = redact_text(text[:4000])
                safe_args[str(key)] = redacted
            else:
                safe_args[str(key)] = text
    payload: dict[str, Any] = {"event": event, "tool": tool, "arguments": safe_args}
    if risk:
        payload["risk"] = risk
    return payload


def payloads_for_result(result: Any) -> dict[str, Any]:
    return {
        "status": getattr(result, "status", ""),
        "summary": redact_text(str(getattr(result, "summary", ""))[: MAX_HOOK_OUTPUT_CHARS])[0],
        "exit_code": getattr(result, "exit_code", None),
    }


__all__ = [
    "HOOK_EVENTS",
    "HOOKS_FILENAME",
    "HookConfigError",
    "HookOutcome",
    "HookRunner",
    "HookSpec",
]
