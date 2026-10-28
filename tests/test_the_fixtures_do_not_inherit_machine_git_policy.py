"""夹具仓库不许继承这台机器的 git 用户级策略

测到的形状（2026-10-28）：本机 ``~/.gitconfig`` 把 ``core.hooksPath`` 指向一个
真实钩子目录。于是每个临时夹具仓库的 ``git commit`` 都在跑**仓库之外**的策略：
300 个文件的变更面板夹具停了十分钟以上（ROADMAP 记过同一位置 14 分钟的停摆），
而且那条钩子的密钥扫描可以直接把夹具提交判拒——夹具的判决因此取决于装了什么
钩子的机器。

``conftest.py`` 的会话夹具把 git 的**用户级**配置（连同它回退的 XDG 配置）指向
一个空文件。这份门两向见证同一个钩子：

* 隔离在场时，``$HOME/.gitconfig`` 里的钩子不跑；
* 拿掉 ``GIT_CONFIG_GLOBAL`` 后，同一个钩子会跑——证明见证本身有效，
  不是钩子写坏了还判绿。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _run(
    args: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def _home_with_a_hook(tmp_path: Path) -> tuple[Path, Path]:
    """A home whose user-global config points at a hook that records its run."""
    home = tmp_path / "home"
    home.mkdir()
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    sentinel = tmp_path / "hook_ran.txt"
    hook = hooks / "pre-commit"
    hook.write_text(
        "#!/bin/sh\nprintf ran > '%s'\n" % sentinel.as_posix(), encoding="utf-8"
    )
    hook.chmod(0o755)
    (home / ".gitconfig").write_text(
        "[core]\n\thooksPath = %s\n" % hooks.as_posix(), encoding="utf-8"
    )
    return home, sentinel


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "t@example.test"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    _run(["git", "add", "-A"], repo)
    return repo


def _commit(repo: Path, *, drop_user_global: bool) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if drop_user_global:
        env.pop("GIT_CONFIG_GLOBAL", None)
    result = _run(["git", "commit", "-m", "x"], repo, env=env)
    assert result.returncode == 0, (
        f"the fixture commit itself failed: {result.stderr.strip()}"
    )
    return result


def test_the_effective_user_config_carries_no_policy(tmp_path: Path) -> None:
    """Pin the mechanism through git's own reader: no user-global entries at all.

    A ``core.hooksPath`` entry is the defect that was measured, but the rule is
    wider: any user-global entry (``core.quotepath``, ``init.defaultBranch``, an
    identity) would let machine policy shape what the fixtures see. Key names
    only in the message - a user config's values are the user's own.
    """
    setting = os.environ.get("GIT_CONFIG_GLOBAL")
    assert setting, (
        "conftest.py must point git's user-global config at an isolated file; "
        "fixture verdicts otherwise depend on the machine's ~/.gitconfig"
    )
    listed = _run(["git", "config", "--global", "--list"], tmp_path)
    assert listed.returncode == 0, listed.stderr
    keys = [
        line.split("=", 1)[0].strip()
        for line in listed.stdout.splitlines()
        if line.strip()
    ]
    assert keys == [], (
        f"git still reads {len(keys)} entr{'y' if len(keys) == 1 else 'ies'} "
        "from the user-global config; a fixture verdict must not be decided by "
        "machine policy: " + ", ".join(keys[:8])
    )


def test_a_home_level_hook_is_not_run_by_a_fixture_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect: a fixture commit must not run the machine's commit hook."""
    home, sentinel = _home_with_a_hook(tmp_path)
    repo = _repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    _commit(repo, drop_user_global=False)
    assert not sentinel.exists(), (
        "a fixture commit ran the hook from the user-global git config; the "
        "suite's verdict is being decided by machine policy outside the repo"
    )


def test_the_same_hook_runs_once_the_isolation_is_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the hook is real, so the green above belongs to the isolation."""
    home, sentinel = _home_with_a_hook(tmp_path)
    repo = _repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    _commit(repo, drop_user_global=True)
    assert sentinel.exists(), (
        "the witness hook did not run even with no GIT_CONFIG_GLOBAL: the "
        "green isolation test above would then prove nothing"
    )
