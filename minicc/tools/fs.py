"""Filesystem tool handlers built on the safe Editor core.

Output discipline (from specproof): every text body is redacted and
head/tail-truncated; read results are line-numbered cat -n style; errors
raise ToolError so the registry converts them to [TOOL_ERROR] results.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any

from .editor import EditError, Editor, StaleContextError
from .registry import ToolError, split_output
from .schemas import ToolResult

MAX_GLOB_RESULTS = 200
MAX_GREP_MATCHES = 100
GREP_CONTEXT_CHARS = 200
TREE_MAX_DEPTH = 4
TREE_MAX_ENTRIES = 400
SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules",
    ".minicc", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist",
    "build", ".idea", ".vscode", "target", ".graders",
}

SENSITIVE_NAMES = {
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def _is_sensitive_path(path: str) -> bool:
    name = Path(path).name.lower()
    if name in SENSITIVE_NAMES or name.endswith(SENSITIVE_SUFFIXES):
        return True
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def _reject_sensitive(path: str) -> None:
    if _is_sensitive_path(path):
        raise ToolError(f"拒绝访问敏感文件: {path} (请由用户手动处理密钥)")


# M4-T5: hidden grader drivers must be invisible AND immutable for the agent —
# recursive discovery skips the directory (SKIP_DIRS) and any explicit path
# touching it is rejected at every file-tool entry point.
GRADER_DIR_NAME = ".graders"


def _reject_graders(path: str) -> None:
    parts = Path(str(path).replace("\\", "/")).parts
    if any(part.lower() == GRADER_DIR_NAME for part in parts):
        raise ToolError(f"拒绝访问评测隐藏目录 {GRADER_DIR_NAME}: {path}")


# M2-T2: the agent must never bootstrap its own permissions or read its own
# credentials. Files under .minicc/ that gate authorization are matched by
# full path suffix (not bare name), denied for both read and write; mcp.json
# stays readable but with header values redacted.
_MINICC_DENY_FILES = {"allowlist.json", "web_token.json", "audit.jsonl", "hooks.json"}
_MINICC_REDACT_FILES = {"mcp.json"}


def _minicc_relative_parts(path: str) -> tuple[str, ...]:
    parts = Path(str(path).replace("\\", "/")).parts
    lowered = tuple(p.lower() for p in parts)
    if ".minicc" not in lowered:
        return ()
    return tuple(p.lower() for p in lowered[lowered.index(".minicc") + 1:])


def _minicc_sensitive_kind(path: str) -> str | None:
    tail = _minicc_relative_parts(path)
    if not tail:
        return None
    name = "/".join(tail)
    if name in _MINICC_DENY_FILES or (tail[0] == "worker" and name.endswith(".config.json")):
        return "deny"
    if name in _MINICC_REDACT_FILES:
        return "redact"
    return None


def _reject_minicc_sensitive(path: str) -> None:
    if _minicc_sensitive_kind(path) is not None:
        raise ToolError(f"拒绝访问 .minicc 下的认证/授权文件: {path} (请由用户在工作区外手动处理)")


MAX_GREP_FILE_BYTES = 2_000_000


def _escapes_workspace(path: Path, workspace: Path) -> bool:
    """True when a directory entry's real target leaves the workspace.

    Windows junctions report is_symlink()==False, so name-based checks miss
    them; the only honest gate is resolve() + is_relative_to() per entry.
    """
    try:
        return not path.resolve().is_relative_to(workspace)
    except OSError:
        return True


def _redact_mcp_headers(text: str) -> str:
    try:
        data = json.loads(text)
    except ValueError:
        return text
    servers = data.get("servers") if isinstance(data, dict) else None
    if isinstance(servers, dict):
        for entry in servers.values():
            if isinstance(entry, dict) and isinstance(entry.get("headers"), dict):
                entry["headers"] = {key: "[REDACTED]" for key in entry["headers"]}
    return json.dumps(data, ensure_ascii=False, indent=2)


def _file_result(text: str, summary: str, **data: Any) -> ToolResult:
    head, tail, truncated = split_output(text)
    return ToolResult(
        status="ok", summary=summary, head=head, tail=tail,
        truncated=truncated, data=dict(data),
    )


def _digest_note(editor: Editor, path: str) -> str:
    return editor.file_digest(path)[:12]


class FsTools:
    """Bound to one workspace Editor instance."""

    def __init__(self, editor: Editor) -> None:
        self.editor = editor

    # -- handlers ------------------------------------------------------------

    def read_file(self, args: dict[str, Any]) -> ToolResult:
        path = str(args["path"])
        _reject_sensitive(path)
        _reject_graders(path)
        minicc_kind = _minicc_sensitive_kind(path)
        if minicc_kind == "deny":
            raise ToolError(f"拒绝读取 .minicc 下的认证/授权文件: {path} (请由用户在工作区外手动处理)")
        offset = int(args.get("offset", 1))
        limit = int(args.get("limit", 2000))
        try:
            lines = self.editor.read_file(path, offset=offset, limit=limit)
        except EditError as exc:
            raise ToolError(str(exc)) from exc
        rendered = "\n".join(
            f"{number:>6}\t{line.rstrip()}" for number, line in lines
        )
        if minicc_kind == "redact":
            try:
                raw_lines: list[str] = []
                start = 1
                while True:
                    chunk = self.editor.read_file(path, offset=start, limit=2000)
                    if not chunk:
                        break
                    raw_lines.extend(line for _number, line in chunk)
                    start += len(chunk)
                    if len(chunk) < 2000:
                        break
                rendered = _redact_mcp_headers("\n".join(raw_lines))
            except EditError as exc:
                raise ToolError(str(exc)) from exc
        if not rendered:
            raise ToolError(
                f"读取窗口为空或越界: {path} (offset={offset}, limit={limit})；"
                "请调整 offset，或确认文件不是空文件"
            )
        return _file_result(
            rendered,
            f"读取 {path} (行 {offset}-{offset + len(lines) - 1}, digest {_digest_note(self.editor, path)}…)",
            digest=self.editor.file_digest(path),
        )

    def write_file(self, args: dict[str, Any]) -> ToolResult:
        path = str(args["path"])
        _reject_sensitive(path)
        _reject_graders(path)
        _reject_minicc_sensitive(path)
        content = str(args["content"])
        expected = args.get("expected_digest") or None
        try:
            self.editor.write_file(path, content, expected_digest=expected)
        except StaleContextError as exc:
            raise ToolError(f"{exc} — 请重新 read_file 后再写") from exc
        except EditError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(
            status="ok",
            summary=(
                f"写入 {path} ({len(content)} chars, "
                f"新 digest {_digest_note(self.editor, path)}…)"
            ),
            data={"digest": self.editor.file_digest(path)},
        )

    def edit_file(self, args: dict[str, Any]) -> ToolResult:
        path = str(args["path"])
        _reject_sensitive(path)
        _reject_graders(path)
        _reject_minicc_sensitive(path)
        old = str(args["old"])
        new = str(args["new"])
        expected = args.get("expected_digest") or None
        try:
            self.editor.apply_edit(path, old, new, expected_digest=expected)
        except StaleContextError as exc:
            raise ToolError(f"{exc} — 请重新 read_file 后再编辑") from exc
        except EditError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(
            status="ok",
            summary=f"编辑 {path} ({len(old)}→{len(new)} chars, 新 digest {_digest_note(self.editor, path)}…)",
            data={"digest": self.editor.file_digest(path)},
        )

    def glob(self, args: dict[str, Any]) -> ToolResult:
        pattern = str(args["pattern"])
        base = Path(args["path"]) if args.get("path") else Path(".")
        _reject_graders(str(base))
        try:
            root = (self.editor.workspace / base).resolve()
            if not root.is_relative_to(self.editor.workspace):
                raise ToolError(f"路径越界: {base}")
            matches = sorted(
                p.relative_to(self.editor.workspace).as_posix()
                for p in root.rglob(pattern)
                if any(part in SKIP_DIRS for part in p.parts[len(root.parts):]) is False
                and not _escapes_workspace(p, self.editor.workspace.resolve())
            )
        except ToolError:
            raise
        except (OSError, ValueError) as exc:
            raise ToolError(f"glob 失败: {exc}") from exc
        shown = matches[:MAX_GLOB_RESULTS]
        body = "\n".join(shown) or "(无匹配)"
        return _file_result(
            body,
            f"glob '{pattern}' 命中 {len(matches)} 个"
            + (f" (仅显示前 {MAX_GLOB_RESULTS})" if len(matches) > MAX_GLOB_RESULTS else ""),
        )

    def grep(self, args: dict[str, Any]) -> ToolResult:
        pattern = str(args["pattern"])
        include = str(args["include"]) if args.get("include") else None
        max_matches = int(args.get("max_matches", MAX_GREP_MATCHES))
        base = Path(args["path"]) if args.get("path") else Path(".")
        _reject_graders(str(base))
        root = (self.editor.workspace / base).resolve()
        if not root.is_relative_to(self.editor.workspace):
            raise ToolError(f"路径越界: {base}")
        if not root.exists():
            raise ToolError(f"grep 路径不存在: {base}")
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ToolError(f"正则非法: {exc}") from exc
        matches: list[str] = []
        files_scanned = 0
        ws_root = self.editor.workspace.resolve()
        try:
            if root.is_file():
                candidates = [root] if not include or fnmatch.fnmatch(root.name, include) else []
            else:
                candidates = sorted(root.rglob(include or "*"))
        except (OSError, ValueError) as exc:
            raise ToolError(f"grep 失败: {exc}") from exc
        for path in candidates:
            if len(matches) >= max_matches:
                break
            rel = path.relative_to(self.editor.workspace)
            if any(part in SKIP_DIRS for part in rel.parts[:-1]):
                continue
            if not path.is_file():
                continue
            if _escapes_workspace(path, ws_root):
                continue
            try:
                if path.stat().st_size > MAX_GREP_FILE_BYTES:
                    continue
            except OSError:
                continue
            if _is_sensitive_path(rel.as_posix()):
                continue
            if include and not fnmatch.fnmatch(path.name, include):
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:4096]:
                continue  # binary
            files_scanned += 1
            try:
                text = raw.decode("utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    rel_posix = rel.as_posix()
                    snippet = line.strip()[:GREP_CONTEXT_CHARS]
                    matches.append(f"{rel_posix}:{line_no}: {snippet}")
                    if len(matches) >= max_matches:
                        break
        body = "\n".join(matches) or "(无匹配)"
        return _file_result(
            body,
            f"grep '{pattern}' 扫描 {files_scanned} 文件命中 {len(matches)} 处",
        )

    def tree(self, args: dict[str, Any]) -> ToolResult:
        base = Path(args["path"]) if args.get("path") else Path(".")
        _reject_graders(str(base))
        max_depth = int(args.get("max_depth", TREE_MAX_DEPTH))
        max_entries = int(args.get("max_entries", TREE_MAX_ENTRIES))
        root = (self.editor.workspace / base).resolve()
        if not root.is_relative_to(self.editor.workspace):
            raise ToolError(f"路径越界: {base}")
        lines: list[str] = [base.as_posix().rstrip("/") or "."]
        ws_root = self.editor.workspace.resolve()

        def walk(directory: Path, depth: int) -> None:
            if depth > max_depth or len(lines) >= max_entries:
                return
            try:
                children = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
            except OSError:
                return
            for child in children:
                if len(lines) >= max_entries:
                    lines.append("… (达到条目上限)")
                    return
                if child.name in SKIP_DIRS:
                    continue
                if _escapes_workspace(child, ws_root):
                    continue
                rel = child.relative_to(root)
                branch = "  " * depth
                if child.is_dir():
                    lines.append(f"{branch}{rel.as_posix()}/")
                    walk(child, depth + 1)
                else:
                    lines.append(f"{branch}{rel.as_posix()}")

        walk(root, 1)
        return _file_result("\n".join(lines), f"目录树 {base.as_posix()} (深度≤{max_depth})")
