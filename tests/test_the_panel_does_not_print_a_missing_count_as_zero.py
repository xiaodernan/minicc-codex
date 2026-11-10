"""M8-T570（第五百五十二批）：面板把「这一格没有数」印成 `+0`。

第五百五十一批以后，后端在数不出来的时候答 `None`（`minicc/changes.py` 的行与总数），
JSON 里是 `null`。可面板每一处都是 `Number(x || 0)` / `compactNumber(x || 0)`：
`null || 0` 是 `0`，屏幕上「没有答案」和「真的是 0 行」是同一句话。
`scratch/probe570c.py` 把 shipped 的 `web/app.js` 里那几个纯函数切出来在 node 里真跑，
量到 `null` / `0` / 键缺失三种现场渲染出的字符串逐字相同（`已修改 · +0 -0`）。

这一门的多数格子**跑的是发出去的那份字节**（`web/app.js`），不是源文本：用户看到的是
bundle，改源不重打包在这里会直接红。构建工具链在不在不影响本门（它不比哈希），
但 `node` 不在的时候行为格 skip——与 `test_web_assets_are_fresh.py` 的 P3 同一个理由。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BUNDLE = REPO / "web" / "app.js"
STREAM = REPO / "web" / "src" / "chat" / "stream.js"
PREVIEW = REPO / "web" / "src" / "files" / "preview.js"
I18N = REPO / "web" / "src" / "core" / "i18n.js"

LABEL_KEY = "changes.uncounted"
ABSENT_KEY = "changes.definitely_not_a_key"
HELPER = "countLabel"

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")

RUN_NAMES = [
    "t",
    "escapeHtml",
    "fileType",
    "changeStatusLabel",
    "compactNumber",
    "changeFileRow",
    "renderChanges",
    HELPER,
]


def _text(path: Path) -> str:
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def _headers(name: str) -> tuple[str, ...]:
    return (
        f"function {name}(",
        f"export function {name}(",
        f"var {name} = (",
        f"const {name} = (",
        f"var {name} = {{",
        f"const {name} = {{",
    )


def _slice(text: str, name: str) -> str:
    for header in _headers(name):
        start = text.find(header)
        if start < 0:
            continue
        depth = 0
        for k in range(text.index("{", start), len(text)):
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : k + 1]
        raise AssertionError(f"{name}: unbalanced braces")
    return ""


def _extract(text: str, names: list[str]) -> dict[str, str]:
    return {name: _slice(text, name) for name in names}


def _js(tmp_path: Path, pieces: dict[str, str], body: str) -> dict[str, str]:
    """把切出来的函数与桩（`state` / `$` / `refreshIcons`）拼成一个 node 模块跑一遍。"""
    i18n = _slice(_text(BUNDLE), "I18N")
    assert i18n, "the I18N literal is not in the shipped bundle"
    lines = [
        i18n + ";",
        'const state = { locale: "zh" };',
        "const captured = {};",
        "const $ = (sel) => ({ set innerHTML(v) { captured[sel] = v; },"
        " set textContent(v) { captured[sel] = v; } });",
        "const refreshIcons = () => {};",
        'const strip = (html) => html.replace(/<[^>]*>/g, " ").replace(/\\s+/g, " ").trim();',
        'console.log("CELL|label|" + strip(t("' + LABEL_KEY + '")));',
        'console.log("CELL|fallback|" + t("' + ABSENT_KEY + '"));',
    ]
    for name in RUN_NAMES:
        piece = pieces.get(name, "")
        if piece:
            lines.append(piece)
    lines.append(body)
    script = tmp_path / "harness570.mjs"
    script.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    cells: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0] == "CELL":
            cells[parts[1]] = parts[2].strip()
    assert "label" in cells, proc.stdout
    return cells


ROW_BODY = """
const cases = {
  none: { path: "a.md", status: "modified", additions: null, deletions: null },
  zero: { path: "a.md", status: "modified", additions: 0, deletions: 0 },
  absent: { path: "a.md", status: "modified" },
  real: { path: "a.md", status: "modified", additions: 3, deletions: 1 },
};
for (const name of Object.keys(cases)) {
  console.log("CELL|" + name + "|" + strip(changeFileRow(cases[name])));
}
renderChanges({ files: [cases.none], additions: null, deletions: null });
console.log("CELL|summary_none|" + strip(captured["#changeSummary"]));
renderChanges({ files: [cases.zero], additions: 0, deletions: 0 });
console.log("CELL|summary_zero|" + strip(captured["#changeSummary"]));
renderChanges({ files: [cases.real], additions: 1500, deletions: 2 });
console.log("CELL|summary_real|" + strip(captured["#changeSummary"]));
"""


@pytest.fixture(scope="module")
def bundle_pieces() -> dict[str, str]:
    return _extract(_text(BUNDLE), RUN_NAMES)


# --------------------------------------------------------------------------
# 跑 shipped 的字节：没有数的那一格不许印成 0
# --------------------------------------------------------------------------

@needs_node
def test_a_row_with_no_count_does_not_print_zero(tmp_path, bundle_pieces) -> None:
    cells = _js(tmp_path, bundle_pieces, ROW_BODY)
    label = cells["label"]
    assert label != LABEL_KEY, "那个词在 i18n 里没有家，屏幕上印的是键名"
    assert cells["none"].count(label) == 2, cells["none"]
    assert "+0" not in cells["none"], cells["none"]
    assert "-0" not in cells["none"], cells["none"]


@needs_node
def test_the_missing_count_and_a_real_zero_are_not_the_same_sentence(tmp_path, bundle_pieces) -> None:
    """`null` 与「这个键没来」是同一件事（都没有数），`0` 是另一件事。"""
    cells = _js(tmp_path, bundle_pieces, ROW_BODY)
    assert cells["none"] != cells["zero"], (cells["none"], cells["zero"])
    assert cells["none"] == cells["absent"], (cells["none"], cells["absent"])


@needs_node
def test_the_summary_with_no_count_does_not_print_zero(tmp_path, bundle_pieces) -> None:
    cells = _js(tmp_path, bundle_pieces, ROW_BODY)
    assert "+ 0" not in cells["summary_none"], cells["summary_none"]
    assert cells["label"] in cells["summary_none"], cells["summary_none"]


# --------------------------------------------------------------------------
# 控制格：落地前后都得绿——本批不许改口已有的数
# --------------------------------------------------------------------------

@needs_node
def test_the_control_a_real_count_still_prints_its_number(tmp_path, bundle_pieces) -> None:
    cells = _js(tmp_path, bundle_pieces, ROW_BODY)
    assert "+3" in cells["real"], cells["real"]
    assert "-1" in cells["real"], cells["real"]


@needs_node
def test_the_control_a_zero_still_prints_zero(tmp_path, bundle_pieces) -> None:
    cells = _js(tmp_path, bundle_pieces, ROW_BODY)
    assert "+0" in cells["zero"], cells["zero"]
    assert "-0" in cells["zero"], cells["zero"]


@needs_node
def test_the_control_the_summary_still_compacts_a_big_number(tmp_path, bundle_pieces) -> None:
    cells = _js(tmp_path, bundle_pieces, ROW_BODY)
    assert "+ 1.5k" in cells["summary_real"], cells["summary_real"]


@needs_node
def test_the_control_a_missing_label_falls_back_to_the_key(tmp_path, bundle_pieces) -> None:
    """词没有家时屏幕上印的是键名——所以「双语都有这一个键」是门，不是装饰。"""
    cells = _js(tmp_path, {"t": bundle_pieces["t"]}, 'console.log("CELL|idle|1");')
    assert cells["fallback"] == ABSENT_KEY, cells


# --------------------------------------------------------------------------
# 一个事实一个家：词、判法、六处现场、发出去的那份字节
# --------------------------------------------------------------------------

def test_the_word_for_no_count_has_one_home_in_both_locales() -> None:
    body = _text(I18N)
    zh = body[body.index("zh:") : body.index("en:")]
    en = body[body.index("en:") :]
    for block, name in ((zh, "zh"), (en, "en")):
        assert f'"{LABEL_KEY}"' in block, f"{name} 没有这个词"
        value = block.split(f'"{LABEL_KEY}":', 1)[1].split(",", 1)[0].strip()
        assert value and value != f'"{LABEL_KEY}"', (name, value)


def test_the_bundle_carries_the_word_in_both_locales() -> None:
    """改完源不重打包，屏幕上什么也不会变：这一格盯的就是那一件事。"""
    assert _text(BUNDLE).count(f'"{LABEL_KEY}"') >= 2, _text(BUNDLE).count(f'"{LABEL_KEY}"')


def test_no_count_site_borrows_zero_anymore() -> None:
    for path in (STREAM, PREVIEW):
        body = _text(path)
        for field in ("additions", "deletions"):
            assert f"{field} || 0" not in body, (path.name, field)
        assert f"{HELPER}(" in body, path.name


def test_the_row_the_list_and_the_badge_ask_the_same_helper() -> None:
    """四处现场、两个数：至少八次问话，都在同一个帮手上。"""
    assert _text(BUNDLE).count(f"{HELPER}(") >= 8, _text(BUNDLE).count(f"{HELPER}(")


def test_the_shipped_helper_is_the_source_helper() -> None:
    """源里那一个帮手与发出去的字节里的那一个必须是同一段代码。

    打包会把注释去掉（esbuild 的默认），所以比的是代码行；注释在不在不是这一格的事。
    """
    from_bundle = _slice(_text(BUNDLE), HELPER)
    from_source = _slice(_text(STREAM), HELPER)
    assert from_bundle, "bundle 里没有这个帮手（源改了没重打包？）"
    assert from_source, "源里没有这个帮手"
    fold = lambda body: [line.strip() for line in body.splitlines()
                         if line.strip() and not line.strip().startswith("//")]
    assert fold(from_bundle) == fold(from_source), (from_source, from_bundle)


def test_the_preview_module_imports_the_one_home() -> None:
    """详情页那一头不许自己再判一次：它 import 那一个家。"""
    line = next((l for l in _text(PREVIEW).splitlines() if 'from "../chat/stream.js"' in l), "")
    assert HELPER in line, line
