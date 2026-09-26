"""Select explicit, bounded checks from changed files and project configuration."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from .check_commands import command_parts, checker_invocation
from .test_selection import relevant_python_tests

_DIGEST_CACHE: OrderedDict[str, tuple[tuple[int, int, int], bytes]] = OrderedDict()
_DIGEST_LOCK = threading.Lock()


def _file_digest(path: Path, *, use_cache: bool = True) -> bytes:
    """Hash one file, optionally refusing to answer from the memo.

    use_cache=False is for the paths a task actually changed: the verifier's
    before/after guard compares two fingerprints, so a memo hit on a changed file makes
    the staleness symmetric and the guard passes while never having hashed the current
    bytes at all. Those paths are few, so re-reading them is the cheap side of the trade.

    Residual window, accepted deliberately: an equal-length in-place rewrite that does not
    advance st_mtime_ns (measured at ~32% of rapid writes on one volume, and ~0 outside a
    sub-millisecond gap) is invisible to this key even with st_ino, because the identity
    term only separates different incarnations of a path. The web loop cannot produce it -
    a memo entry is installed inside the verify step, and every later write to that file is
    separated from it by a model round trip - so the exposure is bounded by that ordering
    rather than by the timestamp. Widening the key further would cost the memo its purpose.
    """
    stat = path.stat()
    # st_ino leads the signature: on a volume where the write timestamp is coarse, a
    # deleted-and-recreated file can present the same (mtime_ns, ctime_ns, size) as the
    # incarnation whose digest is cached, and the cache would then answer for bytes that
    # are no longer the ones it hashed. st_ino is what distinguishes those two lives.
    signature = (stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    key = str(path)
    if use_cache:
        with _DIGEST_LOCK:
            cached = _DIGEST_CACHE.get(key)
            if cached and cached[0] == signature:
                _DIGEST_CACHE.move_to_end(key)
                return cached[1]
    value = hashlib.sha256(path.read_bytes()).digest()
    after = path.stat()
    if (after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size) != signature:
        raise OSError("verification input changed while hashing")
    with _DIGEST_LOCK:
        _DIGEST_CACHE[key] = (signature, value)
        while len(_DIGEST_CACHE) > 4096:
            _DIGEST_CACHE.popitem(last=False)
    return value


@dataclass(frozen=True)
class VerificationCommand:
    command: str
    label: str = "pytest"
    timeout: int = 120


@dataclass
class VerificationPlan:
    commands: list[VerificationCommand] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    fingerprint: str = ""
    reason: str = ""


def verification_fingerprint(root: Path, changed: list[str], commands: list[VerificationCommand]) -> str:
    """Bounded dependency identity; uncertain/incomplete scans disable reuse."""
    root = root.resolve()
    digest = hashlib.sha256(str(root).encode())
    cacheable = True
    scanned = 0
    total_bytes = 0
    suffixes = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".toml", ".css", ".html", ".yaml", ".yml", ".txt", ".csv", ".tsv", ".xml", ".ini", ".cfg", ".lock", ".sql", ".vue", ".svelte", ".md", ".markdown", ".rst", ".adoc", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".c", ".h", ".cc", ".cpp", ".hpp", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".swift", ".scss", ".sass", ".less", ".diff", ".patch"}
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {".git", ".venv", ".minicc", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".playwright-cli", "venv", "node_modules", "output", "__pycache__", "dist", "build"} and not (Path(current) / d).is_symlink())
        for name in sorted(files):
            path = Path(current) / name
            # Environment/secret inputs are intentionally not read into a
            # verification snapshot. Their presence disables reuse instead.
            if name == ".env" or name.startswith(".env.") or path.suffix in {".pem", ".key"}:
                cacheable = False
                continue
            hidden_config = name.startswith(".") or any(part.startswith(".") for part in path.relative_to(root).parts[:-1])
            # M4-T1: extensionless build files (Makefile/Dockerfile/LICENSE) and
            # doc/script/binary suffixes must enter the fingerprint too, otherwise
            # editing them reuses a stale passing cache.
            if not hidden_config and path.suffix not in suffixes and path.suffix != "":
                continue
            scanned += 1
            try:
                stat = path.stat()
                total_bytes += stat.st_size
                if scanned > 8192 or total_bytes > 64_000_000:
                    return ""
                if path.is_symlink() or stat.st_size > 2_000_000:
                    cacheable = False
                    continue
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(_file_digest(path))
            except OSError:
                cacheable = False
    config_path = root / ".minicc" / "verification.json"
    for relative in [*changed, *([".minicc/verification.json"] if config_path.exists() else [])]:
        path = root / relative
        digest.update(relative.encode())
        try:
            if not path.exists():
                digest.update(b"deleted")
            elif path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root) and path.stat().st_size <= 2_000_000:
                digest.update(_file_digest(path, use_cache=False))
            else:
                cacheable = False
        except OSError:
            cacheable = False
    digest.update(json.dumps([(c.command, c.label, c.timeout) for c in commands]).encode())
    return digest.hexdigest() if cacheable else ""


def changed_paths_from_events(events: list[dict[str, Any]]) -> list[str]:
    return sorted({str(event.get("path")) for event in events
                   if event.get("status") == "ok" and event.get("write") and event.get("path")})


def _quote(path: str) -> str:
    # Commands run under either cmd or a POSIX shell; double quoted paths
    # are portable after rejecting shell metacharacters in the verifier.
    return '"' + path.replace('"', '') + '"'


def _matches(path: str, pattern: str) -> bool:
    # pathlib.Path.match treats ** like one path component on Python 3.11.
    # These project rules use standard recursive-glob semantics.
    expression = ""
    i = 0
    while i < len(pattern):
        if pattern[i:i + 3] == "**/":
            expression += "(?:.*/)?"
            i += 3
        elif pattern[i:i + 2] == "**":
            expression += ".*"
            i += 2
        elif pattern[i] == "*":
            expression += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            expression += "[^/]"
            i += 1
        else:
            expression += re.escape(pattern[i])
            i += 1
    return re.fullmatch(expression, path.replace("\\", "/")) is not None


def build_verification_plan(workspace: Path, changed_paths: list[str] | None = None, *, full: bool = False) -> VerificationPlan:
    root = workspace.resolve()
    changed = sorted({Path(path).as_posix() for path in changed_paths or []
                      if not Path(path).is_absolute() and (root / path).resolve().is_relative_to(root)})
    commands: list[VerificationCommand] = []
    config_path = root / ".minicc" / "verification.json"
    if config_path.is_file():
        if config_path.is_symlink() or not config_path.resolve().is_relative_to(root):
            raise ValueError("verification.json 必须位于工作区内")
        if config_path.stat().st_size > 64_000:
            raise ValueError("verification.json 超过 64KB")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or not isinstance(config.get("rules", []), list):
            raise ValueError("verification.json rules must be an array")
        if len(config.get("rules", [])) > 64:
            raise ValueError("verification.json 最多支持 64 条规则")
        for rule in config.get("rules", []):
            if not isinstance(rule, dict):
                raise ValueError("verification.json 每项 rule 必须为对象")
            patterns = rule.get("paths", ["**"])
            configured = rule.get("commands", [])
            if not isinstance(patterns, list) or not all(isinstance(value, str) for value in patterns):
                raise ValueError("verification.json paths 必须为字符串数组")
            if not isinstance(configured, list) or len(configured) > 16 or not all(isinstance(value, str) and value.strip() for value in configured):
                raise ValueError("verification.json commands 必须为非空命令字符串数组")
            if any(_matches(path, pattern) for path in changed for pattern in patterns):
                commands.extend(VerificationCommand(command, label="project") for command in configured)
    candidates = relevant_python_tests(root, changed)
    if full:
        commands.append(VerificationCommand("python -m pytest -q", label="full regression", timeout=300))
    elif candidates:
        commands.append(VerificationCommand("python -m pytest -q " + " ".join(_quote(path) for path in sorted(candidates))))
    frontend = any(Path(path).suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".html"} for path in changed)
    package = root / "package.json"
    if frontend and package.is_file():
        if package.is_symlink() or not package.resolve().is_relative_to(root):
            raise ValueError("package.json 必须位于工作区内")
        metadata = json.loads(package.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict) or not isinstance(metadata.get("scripts", {}), dict):
            raise ValueError("package.json scripts 必须为对象")
        scripts = metadata.get("scripts", {})
        for name in ("check:web", "typecheck"):
            if name in scripts:
                commands.append(VerificationCommand(f"npm run {name}", name))
    for path in changed:
        if Path(path).suffix in {".js", ".mjs", ".cjs"} and (root / path).is_file():
            commands.append(VerificationCommand("node --check " + _quote(path), "javascript syntax"))
    # No broad fallback. Unknown scope must be reported honestly, not silently
    # expanded to the entire test suite.
    unique = list({command.command: command for command in commands}.values())
    if len(unique) > 64:
        raise ValueError("匹配的自动验证命令超过 64 条，请缩小规则范围")
    fingerprint = verification_fingerprint(root, changed, unique) if unique else ""
    return VerificationPlan(unique, changed, fingerprint, "changed files" if unique else "没有与改动匹配的自动检查，请提供定向验证证据")


def safe_verification_command(command: str, *, allow_project_scripts: bool = False) -> bool:
    from ..tools.bash import is_readonly_command
    from .tool_policy import is_verification_evidence
    if not is_verification_evidence("bash", {"command": command}, "ok"):
        return False
    if is_readonly_command(command):
        return True
    if not command or any(char in command for char in "&|;<>`$()%^!\n\r"):
        return False
    try:
        parts = command_parts(command)
    except ValueError:
        return False
    if len(parts) == 3 and parts[:2] == ["node", "--check"]:
        return not parts[2].startswith("-")
    checker, _ = checker_invocation(command)
    if checker in {"pytest", "unittest"}:
        return True
    # Project scripts execute workspace code: only tasks already authorized
    # for commands may use these checks.
    return allow_project_scripts and len(parts) == 3 and parts[:2] == ["npm", "run"] and parts[2] in {"check:web", "typecheck", "test:unit", "lint"}
