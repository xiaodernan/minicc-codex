"""Optional Docker execution for commands that should not touch the host."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from .tools.bash import run_bash, run_process
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

    def run(
        self,
        command: str,
        workspace: Path,
        timeout: int = 120,
        cancel_event: threading.Event | None = None,
    ) -> ToolResult:
        backend = self.status()["backend"]
        if backend == "unavailable":
            return ToolResult(
                status="error",
                summary="[SANDBOX_UNAVAILABLE] Docker 不可用；未回退到宿主机执行",
                security_tags=["sandbox_unavailable"],
            )
        if backend != "docker":
            return run_bash(command, workspace, timeout=timeout, cancel_event=cancel_event)

        args = [
            "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "256",
            "--read-only", "--tmpfs", "/tmp", "-v", f"{workspace.resolve()}:/workspace:rw",
            "-w", "/workspace", self.image, "sh", "-lc", command,
        ]
        return run_process(
            args,
            workspace,
            timeout=timeout,
            cancel_event=cancel_event,
            shell=False,
            summary_label="Docker 命令",
            security_tags=["sandboxed"],
        )
