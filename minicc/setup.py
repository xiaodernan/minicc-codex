"""M8-T688 — ``minicc --setup``: scaffold a workspace so ``--doctor`` is green.

Creates the files a fresh workspace needs, idempotently and without ever
overwriting user state:

- ``<ws>/.minicc/permissions.json`` — denies ``.env`` and ``secrets/**`` unless
  the file already exists (existing files are never overwritten).
- ``<ws>/.minicc/web_token.json`` — a fresh URL-safe token, mode 0o600.
- ``<ws>/.minicc/`` itself is created if absent.

Prints a stable report.  Exits 0 on success, 1 on any write failure.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

from minicc.allowlist import empty_rule_side
from minicc.internal_paths import PERMISSIONS_NAME, TOKEN_FILE_NAME

DEFAULT_PERMISSIONS: dict[str, dict[str, list[str]]] = {
    "deny": {
        **empty_rule_side(),
        "paths": [".env", ".env.local", "secrets", "secrets/**", ".ssh", ".aws"],
    },
    "allow": empty_rule_side(),
}


@dataclass(frozen=True)
class SetupReport:
    created_dir: bool
    created_permissions: bool
    created_web_token: bool
    message: str
    exit_code: int = 0


def _write_permissions(path: Path) -> None:
    path.write_text(
        json.dumps(DEFAULT_PERMISSIONS, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_token(path: Path) -> None:
    path.write_text(secrets.token_urlsafe(48) + "\n", encoding="utf-8")


def setup_workspace(workspace: Path | str | None = None) -> SetupReport:
    root = Path(workspace) if workspace is not None else Path.cwd()

    state = root / ".minicc"
    lines: list[str] = []
    created_dir = False
    created_permissions = False
    created_web_token = False

    try:
        if not state.exists():
            state.mkdir(parents=True, exist_ok=True)
            created_dir = True
            lines.append(f"created {state}")

        permissions = state / PERMISSIONS_NAME
        if not permissions.exists():
            _write_permissions(permissions)
            created_permissions = True
            lines.append(
                f"wrote {PERMISSIONS_NAME}: deny [.env, .env.local, secrets, secrets/**, .ssh, .aws]"
            )
        else:
            lines.append(f"kept existing {PERMISSIONS_NAME}")

        token = state / TOKEN_FILE_NAME
        if not token.exists():
            _write_token(token)
            created_web_token = True
            try:
                os.chmod(token, 0o600)
            except (OSError, NotImplementedError):
                pass
            lines.append(f"wrote {TOKEN_FILE_NAME}: bearer token (0o600 intended)")
        else:
            lines.append(f"kept existing {TOKEN_FILE_NAME}")
    except OSError as exc:
        return SetupReport(
            created_dir=created_dir,
            created_permissions=created_permissions,
            created_web_token=created_web_token,
            message=f"setup failed: {type(exc).__name__}: {exc}",
            exit_code=1,
        )

    message_lines = [
        "minicc --setup: workspace ready",
        *lines,
    ]
    if created_web_token:
        message_lines.append("web bearer token lives at .minicc/web_token.json — do not commit it")

    return SetupReport(
        created_dir=created_dir,
        created_permissions=created_permissions,
        created_web_token=created_web_token,
        message="\n".join(message_lines),
        exit_code=0,
    )


def main() -> int:
    import argparse

    from .cli_io import cli_out

    parser = argparse.ArgumentParser(
        prog="minicc --setup",
        description="为工作区创建 .minicc/ 骨架（permissions.json + web_token.json）。",
    )
    parser.add_argument("workspace", nargs="?", default=Path.cwd(), type=Path)
    args = parser.parse_args()
    report = setup_workspace(args.workspace)
    cli_out(report.message)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
