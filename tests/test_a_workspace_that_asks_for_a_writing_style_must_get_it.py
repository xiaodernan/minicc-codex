"""M8-T285: a workspace that asks for a writing style must get it.

``minicc/output_style.py`` documents the resolution order as "an explicit
config value first, then the workspace file ``.minicc/output-style.md``", and
``load_output_style`` did implement that order.  But nothing in the
production path ever called it: the prompt was built from
``config.output_style`` alone, so a user who wrote the file got a silently
ignored preference, and the file was only read by a test.

This door pins:

* the workspace file reaches the system prompt;
* an explicit configuration value still wins over the file;
* the controls: no file and no configuration leave the prompt unchanged; a
  preset name still resolves.
"""

from __future__ import annotations

from pathlib import Path

from minicc.prompt import build_system_prompt


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    return workspace


def test_the_workspace_style_file_reaches_the_prompt(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / ".minicc" / "output-style.md").write_text(
        "请用中文写总结，每段不超过三行。\n", encoding="utf-8"
    )
    prompt = build_system_prompt(workspace)
    assert "请用中文写总结" in prompt, (
        "the workspace's own style file was not read by the production path"
    )


def test_an_explicit_configuration_value_wins_over_the_file(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / ".minicc" / "output-style.md").write_text(
        "文件里的风格。\n", encoding="utf-8"
    )
    prompt = build_system_prompt(workspace, output_style="配置里的风格。")
    assert "配置里的风格" in prompt
    assert "文件里的风格" not in prompt


def test_a_preset_name_still_resolves(tmp_path: Path) -> None:
    """The control: the config value may name a preset."""
    workspace = _workspace(tmp_path)
    prompt = build_system_prompt(workspace, output_style="concise")
    assert "输出风格" in prompt
    assert "简短" in prompt


def test_no_file_and_no_configuration_leave_the_prompt_alone(tmp_path: Path) -> None:
    """The control: a workspace without a preference changes nothing."""
    workspace = _workspace(tmp_path)
    prompt = build_system_prompt(workspace)
    assert "输出风格" not in prompt
