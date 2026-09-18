"""Task snapshots and lazy file preimages for scoped, conflict-aware rewind."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_SKIP_PREFIXES = (".minicc/", ".git/")
MAX_SNAPSHOT_FILES = 400
MAX_SNAPSHOT_FILE_BYTES = 16 * 1024 * 1024
MAX_SNAPSHOT_TOTAL_BYTES = 64 * 1024 * 1024


class SnapshotError(RuntimeError):
    """A task snapshot cannot be captured or restored."""


def snapshot_dir(workspace: Path, task_id: str) -> Path:
    if not _SAFE_TASK_ID.fullmatch(str(task_id or "")):
        raise SnapshotError(f"非法 task id: {task_id!r}")
    root = Path(workspace).resolve()
    dest = root / ".minicc" / "snapshots" / task_id
    current = root
    for part in dest.relative_to(root).parts:
        current /= part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise SnapshotError("快照路径不能包含链接")
    if not dest.resolve().is_relative_to(root):
        raise SnapshotError("快照路径超出工作区")
    return dest


def _relative(raw: object) -> str:
    if not isinstance(raw, str) or not raw:
        raise SnapshotError("快照包含空路径")
    rel = raw.replace("\\", "/")
    if "\0" in rel or ":" in rel or PureWindowsPath(rel).drive or PurePosixPath(rel).is_absolute() or ".." in PurePosixPath(rel).parts:
        raise SnapshotError(f"快照路径越界: {rel}")
    parts = PurePosixPath(rel).parts
    if not parts or parts[0].casefold() in {".git", ".minicc"}:
        raise SnapshotError(f"快照包含内部路径: {rel}")
    return rel


def _within(root: Path, rel: str) -> Path:
    if root.is_symlink() or root.resolve() != root.absolute():
        raise SnapshotError("快照文件目录不能包含链接")
    target = root / _relative(rel)
    current = root
    for part in target.relative_to(root).parts:
        current /= part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise SnapshotError(f"快照不跟随文件链接: {rel}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise SnapshotError(f"快照路径越界: {rel}")
    return target


def _git_dirty_files(workspace: Path) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "-uall"], cwd=workspace,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    files: list[str] = []
    seen: set[str] = set()
    records = iter(completed.stdout.split("\0"))
    for raw in records:
        if len(raw) < 4:
            continue
        path = raw[3:]
        if "R" in raw[:2] or "C" in raw[:2]:
            next(records, None)
        if not path or path.casefold().startswith(_SKIP_PREFIXES) or path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def _load(dest: Path, root: Path) -> dict[str, Any]:
    if (dest / "manifest.json").is_symlink():
        raise SnapshotError("快照清单不能是链接")
    try:
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"无法读取快照清单: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise SnapshotError("快照清单格式错误")
    if manifest.get("workspace") and Path(manifest["workspace"]).resolve() != root:
        raise SnapshotError("快照所属工作区不匹配")
    return manifest


def _save(dest: Path, manifest: dict[str, Any]) -> None:
    temp = dest / f".manifest-{secrets.token_hex(6)}.tmp"
    try:
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, dest / "manifest.json")
    finally:
        temp.unlink(missing_ok=True)


def _summary(manifest: dict[str, Any]) -> dict[str, Any]:
    complete = not manifest.get("skipped")
    return {key: manifest.get(key, []) for key in ("task_id", "files", "missing", "skipped")} | {
        "captured": complete, "complete": complete, "partial": not complete,
        "skipped_reasons": manifest.get("skipped_reasons", {}),
    }


def _copy_preimage(source: Path, target: Path, *, used: int, count: int) -> tuple[str, int]:
    stat = source.stat()
    if count >= MAX_SNAPSHOT_FILES or stat.st_size > MAX_SNAPSHOT_FILE_BYTES or used + stat.st_size > MAX_SNAPSHOT_TOTAL_BYTES:
        raise SnapshotError("快照超过文件数或字节上限，未复制此文件")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".preimage-{secrets.token_hex(6)}.tmp"
    try:
        shutil.copy2(source, temporary)
        after = source.stat()
        if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise SnapshotError("快照复制期间源文件已变化")
        digest = _digest(temporary)
        os.replace(temporary, target)
        return str(digest), stat.st_size
    finally:
        temporary.unlink(missing_ok=True)


def capture(workspace: Path, task_id: str) -> dict[str, Any]:
    """Preserve dirty files once; clean files are backed up lazily on writes."""
    root = Path(workspace).resolve()
    dest = snapshot_dir(root, task_id)
    if (dest / "manifest.json").is_file():
        return _summary(_load(dest, root))
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    digests: dict[str, str | None] = {}
    missing: list[str] = []
    skipped: list[str] = []
    reasons: dict[str, str] = {}
    sizes: dict[str, int] = {}
    used = 0
    for rel in _git_dirty_files(root):
        try:
            src = _within(root, rel)
            if not src.is_file():
                missing.append(rel)
                continue
            target = _within(dest / "files", rel)
            digest, size = _copy_preimage(src, target, used=used, count=len(copied))
        except (SnapshotError, OSError) as exc:
            skipped.append(rel)
            reasons[rel] = str(exc)[:240]
            continue
        copied.append(rel)
        digests[rel] = digest
        sizes[rel] = size
        used += size
    manifest = {"version": 2, "task_id": task_id, "files": copied, "digests": digests, "sizes": sizes, "missing": missing, "skipped": skipped, "skipped_reasons": reasons, "workspace": str(root)}
    _save(dest, manifest)
    return _summary(manifest)


def _digest(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise SnapshotError("快照路径已被目录替换")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class SnapshotJournal:
    """Editor hooks preserving the first preimage and the latest task digest."""

    def __init__(self, workspace: Path, task_id: str) -> None:
        self.root = Path(workspace).resolve()
        self.dest = snapshot_dir(self.root, task_id)
        self.lock = threading.RLock()
        manifest = _load(self.dest, self.root)
        manifest.setdefault("touched", {})
        _save(self.dest, manifest)

    def before_write(self, path: Path) -> None:
        rel = path.relative_to(self.root).as_posix()
        with self.lock:
            target = _within(self.root, rel)
            manifest = _load(self.dest, self.root)
            prior = manifest.get("touched", {}).get(rel)
            if prior is not None and ("digest" not in prior or _digest(target) != prior["digest"]):
                raise SnapshotError(f"文件在上次任务写入后发生变化或写入未确认，拒绝覆盖: {rel}")
            if rel in manifest.get("skipped", []):
                raise SnapshotError(f"此文件未取得可靠回退镜像，拒绝编辑: {rel}")
            if rel not in manifest.get("touched", {}) and rel in manifest.get("digests", {}):
                if _digest(target) != manifest["digests"][rel]:
                    raise SnapshotError(f"文件在任务快照后被外部修改，拒绝覆盖: {rel}")
            if rel not in manifest["files"] and rel not in manifest.get("missing", []):
                if target.is_file():
                    source_root = self.dest / "files" if manifest.get("version") == 2 else self.dest
                    backup = _within(source_root, rel)
                    used = sum(int(size) for size in manifest.get("sizes", {}).values())
                    digest, size = _copy_preimage(target, backup, used=used, count=len(manifest["files"]))
                    manifest["files"].append(rel)
                    manifest.setdefault("digests", {})[rel] = digest
                    manifest.setdefault("sizes", {})[rel] = size
                elif not target.exists():
                    manifest.setdefault("missing", []).append(rel)
                else:
                    raise SnapshotError(f"不能备份目录: {rel}")
            manifest.setdefault("touched", {})[rel] = {"pending": True}
            _save(self.dest, manifest)

    def after_write(self, path: Path) -> None:
        rel = path.relative_to(self.root).as_posix()
        with self.lock:
            manifest = _load(self.dest, self.root)
            manifest.setdefault("touched", {})[rel] = {"digest": _digest(_within(self.root, rel))}
            _save(self.dest, manifest)


def restore(workspace: Path, task_id: str) -> dict[str, Any]:
    """Restore journaled files without overwriting later user edits.

    Legacy snapshots only copy their recorded dirty files back. New editor
    journals additionally cover initially clean files and task-created files;
    unrelated files and untracked shell side effects are never deleted.
    """
    root = Path(workspace).resolve()
    dest = snapshot_dir(root, task_id)
    if not (dest / "manifest.json").is_file():
        raise SnapshotError(f"找不到任务快照: {task_id}")
    manifest = _load(dest, root)
    source_root = dest / "files" if manifest.get("version") == 2 else dest
    journal = manifest.get("touched")
    if journal is not None and not isinstance(journal, dict):
        raise SnapshotError("快照写入记录格式错误")
    paths = list(journal) if journal is not None else manifest["files"]
    restored: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []
    conflicts: list[str] = []
    for raw in paths:
        try:
            rel = _relative(raw)
            target = _within(root, rel)
            src = _within(source_root, rel)
            if journal is not None:
                record = journal[raw]
                if not isinstance(record, dict) or "digest" not in record or _digest(target) != record["digest"]:
                    conflicts.append(rel)
                    continue
            if rel in manifest["files"] and src.is_file():
                expected = manifest.get("digests", {}).get(rel)
                if expected is not None and _digest(src) != expected:
                    skipped.append(rel)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.parent / f".{target.name}.restore-{secrets.token_hex(6)}"
                try:
                    shutil.copy2(src, temporary)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
                restored.append(rel)
            elif journal is not None and rel in manifest.get("missing", []):
                target.unlink(missing_ok=True)
                removed.append(rel)
            else:
                skipped.append(rel)
                continue
            if journal is not None:
                journal[rel] = {"digest": _digest(target)}
        except (SnapshotError, OSError):
            skipped.append(str(raw))
    if journal is not None:
        _save(dest, manifest)
    return {"task_id": task_id, "restored": restored, "removed": removed, "skipped": skipped, "conflicts": conflicts}


def exists(workspace: Path, task_id: str) -> bool:
    try:
        return (snapshot_dir(workspace, task_id) / "manifest.json").is_file()
    except SnapshotError:
        return False


__all__ = ["SnapshotError", "SnapshotJournal", "capture", "exists", "restore", "snapshot_dir"]
