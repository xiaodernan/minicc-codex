"""M8-T686 — ``minicc --doctor``: deterministic self-diagnostic for a workspace.

Runs a fixed list of checks against the current workspace and exits with a
verdict the operator can act on.  Never calls the network, never runs the
suite, never writes.  Each check either passes, warns, or fails; a single
``fatal`` verdict fails ``--doctor`` as a whole.

The verdict is machine-readable (``--json``) so this can be wired into CI.
Without ``--json``, it prints a human-friendly report.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from minicc.internal_paths import AUDIT_NAME, PERMISSIONS_NAME, TOKEN_FILE_NAME


@dataclass(frozen=True)
class DoctorCheck:
    """One probe's answer."""

    name: str
    severity: str  # "ok" | "warn" | "fatal"
    detail: str
    fix_hint: str | None = None


CheckResult = list[DoctorCheck]
check_fn: Callable[[Path], DoctorCheck]


def _run(fn: check_fn, workspace: Path) -> DoctorCheck:
    try:
        return fn(workspace)
    except Exception as exc:  # noqa: BLE001 — an unhandled probe is a fatal probe
        return DoctorCheck(
            name=fn.__name__.removeprefix("check_"),
            severity="fatal",
            detail=f"{type(exc).__name__}: {exc}",
            fix_hint="fix the underlying error, then rerun --doctor",
        )


# --- probes (each is small and dumb on purpose) ---


def check_python_version(_workspace: Path) -> DoctorCheck:
    major, minor, micro = sys.version_info[:3]
    ok = (major, minor) >= (3, 11)
    return DoctorCheck(
        "python_version",
        "ok" if ok else "fatal",
        f"python {major}.{minor}.{micro}",
        f"升级到 python>=3.11 (当前: {major}.{minor}.{micro})" if not ok else None,
    )


def check_minicc_import(_workspace: Path) -> DoctorCheck:
    import minicc

    version = getattr(minicc, "__version__", "<no __version__>")
    return DoctorCheck("minicc_import", "ok", f"import ok — {version}")


def check_minicc_compiles(_workspace: Path) -> DoctorCheck:
    """py_compile every file shipped in minicc/.  A syntax failure here means the wheel is stale or the install is partial."""
    import py_compile

    root = Path(__file__).resolve().parent
    failed: list[str] = []
    compiled = 0
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        compiled += 1
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError:
            failed.append(str(path.relative_to(root)))
    if failed:
        return DoctorCheck(
            "module_compiles",
            "fatal",
            f"{len(failed)} modules failed py_compile: {', '.join(failed[:5])}",
            "重装 wheel 或 `pip install -e .`",
        )
    return DoctorCheck("module_compiles", "ok", f"{compiled} modules compiled")


def check_minicc_dir_writable(workspace: Path) -> DoctorCheck:
    state = workspace / ".minicc"
    if not state.exists():
        try:
            state.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return DoctorCheck(
                "minicc_dir_writable",
                "fatal",
                f"cannot create {state}: {exc}",
                "检查目录的写权限",
            )
    probe = state / ".doctor-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return DoctorCheck(
            "minicc_dir_writable",
            "fatal",
            f"workspace .minicc/ is not writable: {exc}",
            "检查 .minicc/ 的所有者与权限",
        )
    return DoctorCheck("minicc_dir_writable", "ok", ".minicc/ writable")


def check_audit_log(workspace: Path) -> DoctorCheck:
    audit = workspace / ".minicc" / AUDIT_NAME
    if not audit.exists():
        return DoctorCheck(
            "audit_log",
            "warn",
            f"no {AUDIT_NAME} yet — nothing to audit",
            "run a real task once to populate the log",
        )
    try:
        last = audit.read_text(encoding="utf-8", errors="replace").splitlines()[-1]
    except (OSError, IndexError) as exc:
        return DoctorCheck(
            "audit_log",
            "warn",
            f"audit log present but unreadable: {exc}",
            "check .minicc/audit.jsonl permissions",
        )
    line = last.strip()
    if not line:
        return DoctorCheck(
            "audit_log",
            "warn",
            "audit log has a trailing blank line",
            "inspect .minicc/audit.jsonl around the last record",
        )
    try:
        json.loads(line)
    except json.JSONDecodeError as exc:
        return DoctorCheck(
            "audit_log",
            "fatal",
            f"last audit record is not valid JSON: {exc}",
            "truncate or repair the line; never silently drop trusted rows",
        )
    return DoctorCheck("audit_log", "ok", "last audit record is valid JSON")


def check_web_token_permissions(workspace: Path) -> DoctorCheck:
    token = workspace / ".minicc" / TOKEN_FILE_NAME
    if not token.exists():
        return DoctorCheck(
            "web_token_permissions",
            "warn",
            f"no {TOKEN_FILE_NAME}; web surface will mint one on first use",
            "export MINICC_WEB_TOKEN or let the web surface create it",
        )
    try:
        mode = token.stat().st_mode & 0o777
    except OSError as exc:
        return DoctorCheck(
            "web_token_permissions",
            "fatal",
            f"cannot stat {TOKEN_FILE_NAME}: {exc}",
            "check permissions on .minicc/web_token.json",
        )
    if mode & 0o077:
        return DoctorCheck(
            "web_token_permissions",
            "fatal",
            f"{TOKEN_FILE_NAME} is mode 0{mode:o}; bearer token must be readable only by the owner",
            f"chmod 600 {token}",
        )
    return DoctorCheck("web_token_permissions", "ok", f"mode 0{mode:o}")


def check_permissions_json(workspace: Path) -> DoctorCheck:
    fpath = workspace / ".minicc" / PERMISSIONS_NAME
    if not fpath.exists():
        return DoctorCheck(
            "permissions_json",
            "warn",
            f"no {PERMISSIONS_NAME}; all calls follow the default mode",
            "copy a minimal allowlist (deny secrets/) if you rely on it",
        )
    from minicc.permissions import load_permission_rules

    try:
        _rules, error = load_permission_rules(workspace)
    except Exception as exc:  # noqa: BLE001
        return DoctorCheck(
            "permissions_json",
            "fatal",
            f"{PERMISSIONS_NAME} not parseable: {type(exc).__name__}: {exc}",
            "validate the JSON; a malformed permissions.json disables the policy entirely",
        )
    if error:
        return DoctorCheck(
            "permissions_json",
            "fatal",
            f"{PERMISSIONS_NAME} error: {error}",
            "fix the syntax error or remove the offending key",
        )
    return DoctorCheck("permissions_json", "ok", f"valid {PERMISSIONS_NAME}")


def check_git_worktree(workspace: Path) -> DoctorCheck:
    from minicc.gitprobe import (
        WORK_TREE_VERDICT_NO,
        WORK_TREE_VERDICT_UNKNOWN,
        work_tree_verdict,
    )

    try:
        kind, detail = work_tree_verdict(workspace)
    except OSError as exc:
        return DoctorCheck(
            "git_worktree",
            "warn",
            f"git probe failed: {exc}",
            "ensure git is on PATH or configure safe.directory",
        )
    if kind == WORK_TREE_VERDICT_NO:
        return DoctorCheck(
            "git_worktree",
            "warn",
            "not a git work tree — benchmarks and change-list cannot run; agent can still edit",
            "run inside a git repository for full functionality",
        )
    if kind == WORK_TREE_VERDICT_UNKNOWN:
        return DoctorCheck(
            "git_worktree",
            "warn",
            f"git probe could not decide if this is a work tree: {detail}",
            "check `git status` manually; if dubious ownership, configure safe.directory",
        )
    return DoctorCheck("git_worktree", "ok", "inside a git work tree")


CHECKS = (
    check_python_version,
    check_minicc_import,
    check_minicc_compiles,
    check_minicc_dir_writable,
    check_audit_log,
    check_web_token_permissions,
    check_permissions_json,
    check_git_worktree,
)


@dataclass(frozen=True)
class DoctorReport:
    ok: int
    warn: int
    fatal: int
    checks: tuple[DoctorCheck, ...]

    @property
    def exit_code(self) -> int:
        return 1 if self.fatal else 0


def run_doctor(workspace: Path | str | None = None) -> DoctorReport:
    root = Path(workspace) if workspace is not None else Path.cwd()
    results: list[DoctorCheck] = []
    for check in CHECKS:
        results.append(_run(check, root))
    ok = sum(1 for c in results if c.severity == "ok")
    warn = sum(1 for c in results if c.severity == "warn")
    fatal = sum(1 for c in results if c.severity == "fatal")
    return DoctorReport(ok=ok, warn=warn, fatal=fatal, checks=tuple(results))


def format_report(report: DoctorReport, *, json_out: bool = False) -> str:
    if json_out:
        return json.dumps(
            {
                "ok": report.ok,
                "warn": report.warn,
                "fatal": report.fatal,
                "checks": [
                    {
                        "name": c.name,
                        "severity": c.severity,
                        "detail": c.detail,
                        "fix_hint": c.fix_hint,
                    }
                    for c in report.checks
                ],
            },
            ensure_ascii=False,
        )
    lines: list[str] = []
    lines.append(f"minicc doctor — ok={report.ok} warn={report.warn} fatal={report.fatal}")
    for check in report.checks:
        mark = {"ok": "[ok]", "warn": "[warn]", "fatal": "[fail]"}[check.severity]
        lines.append(f"{mark} {check.name}: {check.detail}")
        if check.fix_hint:
            lines.append(f"   → {check.fix_hint}")
    return "\n".join(lines)
