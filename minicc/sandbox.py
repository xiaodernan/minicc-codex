"""Optional Docker execution for commands that should not touch the host."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .tools.bash import run_bash
from .tools.schemas import ToolResult


class SandboxRunner:
    """Run host commands by default, or explicit Docker isolation when enabled."""

    def __init__(self, mode: str = "host", image: str = "python:3.11-slim") -> None:
        if mode not in {"host", "docker", "auto"}:
            raise ValueError(f"sandbox mode 非法: {mode!r}")
        self.mode = mode
        self.image = image

    @property
    def docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def status(self) -> dict[str, object]:
        available = self.docker_available
        if self.mode == "docker":
            backend = "docker" if available else "unavailable"
        else:
            backend = "docker" if self.mode == "auto" and available else "host"
        return {
            "mode": self.mode,
            "backend": backend,
            "docker_available": available,
            "image": self.image,
            "isolated": backend == "docker",
        }

    def run(self, command: str, workspace: Path, timeout: int = 120) -> ToolResult:
        backend = self.status()["backend"]
        if backend == "unavailable":
            return ToolResult(
                status="error",
                summary="[SANDBOX_UNAVAILABLE] Docker 不可用；未回退到宿主机执行",
                security_tags=["sandbox_unavailable"],
            )
        if backend != "docker":
            return run_bash(command, workspace, timeout=timeout)

        started = time.monotonic()
        args = [
            "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "256",
            "--read-only", "--tmpfs", "/tmp", "-v", f"{workspace.resolve()}:/workspace:rw",
            "-w", "/workspace", self.image, "sh", "-lc", command,
        ]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return ToolResult(status="timed_out", summary=f"[TIMED_OUT] Docker 命令超时 ({timeout}s)", security_tags=["sandboxed"])
        except OSError as exc:
            return ToolResult(status="error", summary=f"[SANDBOX_ERROR] {exc}", security_tags=["sandbox_error"])
        output = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        from .tools.registry import split_output

        head, tail, truncated = split_output(output)
        return ToolResult(
            status="ok" if proc.returncode == 0 else "error",
            summary=f"(docker exit {proc.returncode}, {time.monotonic() - started:.1f}s)",
            head=head,
            tail=tail,
            truncated=truncated,
            exit_code=proc.returncode,
            security_tags=["sandboxed"],
        )
