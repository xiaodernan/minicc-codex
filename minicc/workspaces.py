"""A tiny persistent catalog of local folders used by the web workspace."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import home_dir
from .logging_setup import get_logger

LOG = get_logger("workspaces")


def resolve_workspace_path(
    raw: object,
    *,
    roots: tuple[object, ...] | list[object] | None = None,
    default: Path | None = None,
) -> Path:
    """Single gate for every workspace entry point (M2-T1).

    Resolves ``raw`` (or ``default`` when empty), requires an existing
    directory, and enforces ``workspace_roots`` when non-empty. All five
    entries — switch_workspace, RPC, /api/chat, task submit, snapshot
    restore — must call this so ``workspace_roots=(A,)`` cannot be
    bypassed with B.
    """
    text = str(raw or "").strip()
    if not text:
        if default is None:
            raise ValueError("工作区路径不能为空")
        candidate = default.expanduser().resolve()
    else:
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve()
    if not candidate.is_dir():
        raise ValueError(f"工作区不是有效目录: {candidate}")
    allowed = [Path(r).expanduser().resolve() for r in (roots or ()) if str(r or "").strip()]
    if allowed and not any(
        candidate == root or candidate.is_relative_to(root) for root in allowed
    ):
        shown = ", ".join(r.as_posix() for r in allowed)
        raise ValueError(
            f"工作区不在允许的目录白名单内: {candidate.as_posix()}（允许: {shown}）"
        )
    return candidate


class WorkspaceCatalog:
    """Remember recently opened folders without storing model credentials."""

    def __init__(self, path: Path | None = None, max_items: int = 12) -> None:
        self.path = path or home_dir() / "workspaces.json"
        self.max_items = max(1, max_items)
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._read()
        output: list[dict[str, Any]] = []
        for item in items:
            raw_path = str(item.get("path") or "")
            if not raw_path:
                continue
            candidate = Path(raw_path)
            output.append(
                {
                    "name": str(item.get("name") or candidate.name or raw_path),
                    "path": raw_path,
                    "exists": candidate.is_dir(),
                    "last_opened": item.get("last_opened"),
                }
            )
        return output

    def remember(self, path: Path) -> None:
        candidate = path.expanduser().resolve()
        record = {
            "name": candidate.name or str(candidate),
            "path": candidate.as_posix(),
            "last_opened": time.time(),
        }
        with self._lock:
            items = [
                item
                for item in self._read()
                if str(item.get("path") or "").lower() != record["path"].lower()
            ]
            items.insert(0, record)
            self._write(items[: self.max_items])

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # M8-T277: ValueError covers both decode failures.  A catalog
            # that is not UTF-8 used to raise a bare UnicodeDecodeError out
            # of here, past the silent-degradation this method promises.
            return []
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    def _write(self, items: list[dict[str, Any]]) -> None:
        """Stage under a name only this write owns, then swap it in as one file.

        workspaces.json is shared by every minicc process on the machine, so a sibling
        named once (``workspaces.tmp``) is a second writer's target too: Windows refuses
        the swap with WinError 32 while that neighbour holds the staging file and WinError 5
        while it holds the destination - both measured.  Losing a recent-folder entry is a
        cosmetic failure; refusing to start a second web server over one is not, so the
        write is best-effort and says where it went, and the staging file never outlives it.
        """
        temporary = self.path.parent / f"{self.path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            LOG.warning(f"工作区目录写不回 {self.path.as_posix()}：{exc}")
            try:
                temporary.unlink()
            except OSError:
                pass


__all__ = ["WorkspaceCatalog", "resolve_workspace_path"]
