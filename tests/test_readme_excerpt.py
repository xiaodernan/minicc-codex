"""The system prompt now opens with the repo's own README excerpt."""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.prompt import _README_EXCERPT_BYTES, build_system_prompt


def test_readme_excerpt_present_and_framed_as_data(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# demo\n\nThis repo does X.\n", encoding="utf-8")
    prompt = build_system_prompt(tmp_path)
    assert "仓库自述" in prompt
    assert "# demo" in prompt
    # the data framing must survive the real README text
    assert prompt.index("仓库自述") < prompt.index("# demo")


def test_readme_excerpt_absent_without_readme(tmp_path: Path) -> None:
    prompt = build_system_prompt(tmp_path)
    assert "仓库自述" not in prompt


def test_readme_excerpt_truncates_to_budget_with_marker(tmp_path: Path) -> None:
    payload = "# big file\n\n" + ("x" * 10_000) + "\nENDING-MARKER\n"
    (tmp_path / "README.md").write_text(payload, encoding="utf-8")
    prompt = build_system_prompt(tmp_path)
    assert "已截断" in prompt
    assert "ENDING-MARKER" not in prompt


def test_readme_excerpt_survives_unreadable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreadable README must not take the whole prompt down with it."""
    target = tmp_path / "README.md"
    target.write_text("# demo\n", encoding="utf-8")

    real = Path.read_bytes

    def boom(self: Path, *args, **kwargs):  # noqa: ANN001, ANN003
        if self == target:
            raise OSError("locked")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", boom)
    prompt = build_system_prompt(tmp_path)
    assert "仓库自述" not in prompt
