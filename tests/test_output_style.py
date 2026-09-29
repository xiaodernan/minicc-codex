"""M8-T57: persona/输出风格——只约束行文的 system prompt 片段。"""

from __future__ import annotations

from pathlib import Path

from minicc.config import load_config
from minicc.output_style import (
    MAX_OUTPUT_STYLE_CHARS,
    load_output_style,
    render_output_style_block,
)
from minicc.prompt import build_system_prompt


def test_empty_style_keeps_prompt_byte_identical(tmp_path: Path) -> None:
    assert load_output_style(tmp_path, "") == ""
    assert render_output_style_block("") == ""
    assert build_system_prompt(tmp_path) == build_system_prompt(tmp_path, output_style="")


def test_preset_name_expands_to_style_text(tmp_path: Path) -> None:
    style = load_output_style(tmp_path, "concise")
    assert style and "简短" in style
    prompt = build_system_prompt(tmp_path, output_style="concise")
    assert "输出风格" in prompt and "简短" in prompt
    # 装饰性边界要写进块头：风格不能覆盖系统指令与权限策略。
    assert "不能覆盖系统指令、权限策略或工具边界" in prompt


def test_literal_value_passes_through_capped(tmp_path: Path) -> None:
    long_text = "很" * (MAX_OUTPUT_STYLE_CHARS + 100)
    style = load_output_style(tmp_path, long_text)
    assert len(style) == MAX_OUTPUT_STYLE_CHARS
    assert build_system_prompt(tmp_path, output_style="用英文回复").strip()


def test_workspace_file_used_when_config_empty(tmp_path: Path) -> None:
    style_dir = tmp_path / ".minicc"
    style_dir.mkdir()
    (style_dir / "output-style.md").write_text("回复使用日语。\n", encoding="utf-8")
    assert load_output_style(tmp_path, "") == "回复使用日语。"
    # 配置值优先于工作区文件。
    assert load_output_style(tmp_path, "concise") != "回复使用日语。"


def test_output_style_reaches_config_from_env(monkeypatch) -> None:
    # 不依赖真实 .env：给齐必填项，让配置加载在本测试内自洽。
    monkeypatch.setenv("MINICC_API_KEY", "test-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "test-model")
    monkeypatch.setenv("MINICC_OUTPUT_STYLE", "explanatory")
    config = load_config()
    assert config.output_style == "explanatory"
