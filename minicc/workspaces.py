"""A tiny persistent catalog of local folders used by the web workspace."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .config import home_dir


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
        except (OSError, json.JSONDecodeError):
            return []
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    def _write(self, items: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)


__all__ = ["WorkspaceCatalog"]
