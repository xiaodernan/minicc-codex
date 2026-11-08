"""M8-T547 — 标注块把 path 原文插进 path="…"：引号一到，名字就断在半路

`minicc/mentions.py` 把每条判决写成 XML 形的 `<file path="…" status="…">`，属性值
是从不转义的原文。扫描器**允许** `"` 出现在 token 里（`t547_probe.py` 量到
`@a"b.txt` 的 token 就是 `a"b.txt`），而未收敛那侧的 `path` 按第五百三十一批的契约
**等于 token**——于是用户打的引号原样落进属性：

    <file path="a"b.txt" status="missing">工作区内没有这个文件</file>

读者（模型，或任何把块当结构化证据的工具）在这里读出的是 `path="a"`，后面
`b.txt"` 成了多余的裸属性。第五百三十一批 §7 第 6 项立案时点的就是这个形状；
本批把它量成断言。注入那侧同一个形状住在 `chunks.append(f'<file path="{rel}">')`，
`rel` 是真实工作区文件的名字：NTFS 不许 `"` 入名，但 `&` 照样能进（`p&q.txt` 在本机
建得出来，`t547_measure2.py` 量到 `<file path="p&q.txt">`），所以两条通道都有腿。

判据不是「转义才好看」：块**自称**是 XML 形的证据，严格的读者读不下去
（`ElementTree` 对 `path="a&b.txt"` 直接 ParseError）。注意两种读者的分工：宽恕的
读者对裸 `<` 照读不误，只有**严格**读者才为它报错——所以 `<`/`>` 两行只能由严格腿
与转义表合同钉住，不能指望往返恢复。本批钉四件事——
①每个 `<file>` 元素恢复出的 path 与记录里的 path 逐字符相等；
②严格读者读得下每一条标注（`&` 与 `<` 两个形状各一格）；
③转义只发生在属性里：正文按块自己的开/闭标记切出来，必须与磁盘上的字节逐字相等，
  两条注句通道（超预算、超条数）是散文不是属性，那里的名字一个字节都不许多；
④四个 XML 元字符各过转义表一行，且 `&` 排第一——引号先折会把 `&quot;` 自己再转一遍。
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from html.parser import HTMLParser
from pathlib import Path

from minicc import mentions as _mentions_module

MODULE_SOURCE = Path(_mentions_module.__file__)

MISSING_TOKEN = 'a"b.txt'
BOTH_TOKEN = 'x&y".txt'
AMP_FILE = "p&q.txt"
AMP_BODY = "AMPBODY"
RAW_BODY = 'body with &amp, <tag> and "quote"\n'
TABLE_ROWS = (
    '.replace("&", "&amp;")',
    '.replace("<", "&lt;")',
    '.replace(">", "&gt;")',
    '.replace(\'"\', "&quot;")',
)


class _Files(HTMLParser):
    """Recover what a lenient reader recovers: the attribute pairs and the text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, str]] = []
        self._pending: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "file":
            return
        self._pending = {key: (value or "") for key, value in attrs}
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._pending is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "file" and self._pending is not None:
            self._pending["#text"] = "".join(self._text)
            self.elements.append(self._pending)
            self._pending = None


def _elements(block: str) -> list[dict[str, str]]:
    parser = _Files()
    parser.feed(block)
    parser.close()
    return parser.elements


def _workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / AMP_FILE).write_text(AMP_BODY + "\n", encoding="utf-8")
    (root / "raw.txt").write_text(RAW_BODY, encoding="utf-8")
    (root / ".minicc").mkdir(exist_ok=True)
    (root / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secret.txt"]}}), encoding="utf-8"
    )
    (root / "secret.txt").write_text("TOP\n", encoding="utf-8")
    return root


def _build(root: Path, message: str, **kwargs):
    from minicc.mentions import build_mention_context

    return build_mention_context(message, root, **kwargs)


def _body_region(block: str, rel: str) -> str:
    """Cut the body out the way the chunk is built: `<file path="…">` + nl + body."""
    open_tag = f'<file path="{rel}">'
    start = block.index(open_tag) + len(open_tag) + 1
    end = block.index("\n</file>", start)
    return block[start:end]


def test_a_quote_in_the_token_does_not_cut_the_path_in_half(tmp_path: Path) -> None:
    """缺陷本体：属性在引号处提前闭合，读者只剩下 `a`。"""
    block, records = _build(_workspace(tmp_path), f"@{MISSING_TOKEN}")
    assert records[0]["path"] == MISSING_TOKEN, records
    elements = _elements(block)
    assert len(elements) == 1, block
    assert elements[0].get("path") == MISSING_TOKEN, elements
    assert elements[0].get("status") == "missing", elements


def test_a_token_mixing_ampersand_and_quote_still_round_trips(tmp_path: Path) -> None:
    block, records = _build(_workspace(tmp_path), f"@{BOTH_TOKEN}")
    elements = _elements(block)
    assert len(elements) == 1, block
    assert elements[0].get("path") == records[0]["path"], (elements, records)


def test_the_annotation_parses_for_a_reader_that_demands_xml(tmp_path: Path) -> None:
    """块自称 XML 形；严格读者今天读不下去——这条不许用异常当判决。

    两格分钉 `&` 与 `<`：宽恕的读者对裸 `<` 照读，只有严格读者会为它报错。
    """
    workspace = _workspace(tmp_path)
    for message, wanted in (("@a&b.txt", "a&b.txt"), ("@a<b>.txt", "a<b>.txt")):
        block, _records = _build(workspace, message)
        element = block[block.index("<file ") : block.index("</file>") + len("</file>")]
        try:
            node = ElementTree.fromstring(f"<root>{element}</root>")
        except ElementTree.ParseError as error:  # turned into an assertion below
            raise AssertionError(
                f"严格读者读不下这一行：{element!r}（{error}）"
            ) from None
        assert node[0].tag == "file", element
        assert node[0].get("path") == wanted, (message, element)


def test_an_injected_name_with_an_ampersand_keeps_its_body(tmp_path: Path) -> None:
    """注入那侧的 `rel` 是真实文件名：NTFS 允许 `&`，同一个形状两条通道都有。"""
    block, records = _build(_workspace(tmp_path), f"@{AMP_FILE}")
    assert records[0]["status"] == "injected", records
    elements = _elements(block)
    assert len(elements) == 1, block
    assert elements[0].get("path") == AMP_FILE, elements
    assert elements[0]["#text"].strip() == AMP_BODY, elements


def test_every_mention_gets_back_the_path_it_was_recorded_with(tmp_path: Path) -> None:
    """派生不变式：恢复出的 path 序列 == 记录里的 path 序列，逐字符。"""
    workspace = _workspace(tmp_path)
    messages = [
        f'@{MISSING_TOKEN}',
        f'@{BOTH_TOKEN}',
        f"@{AMP_FILE}",
        f'@{AMP_FILE} @{MISSING_TOKEN}',
        "@secret.txt",
        "@a<b>.txt",
        "@nosuch.txt",
        "@.minicc/web_token.json",
        f'@{AMP_FILE} @secret.txt @{MISSING_TOKEN}',
    ]
    for message in messages:
        block, records = _build(workspace, message)
        recovered = [item.get("path") for item in _elements(block)]
        expected = [item["path"] for item in records]
        assert recovered == expected, (message, expected, recovered, block)
        for item in _elements(block):
            keys = {key for key in item if key != "#text"}
            assert keys in ({"path"}, {"path", "status"}), (message, item)


def test_the_escaping_never_touches_the_file_body(tmp_path: Path) -> None:
    """转义只许发生在属性里：正文按块自己的标记切出来，与磁盘字节逐字相等。"""
    block, records = _build(_workspace(tmp_path), "@raw.txt")
    assert records[0]["status"] == "injected", records
    assert _body_region(block, "raw.txt") == RAW_BODY, block


def test_the_refusal_still_names_the_verdict_and_its_reason(tmp_path: Path) -> None:
    """转义不是「路径难看就不说」：判决与 reason 都得留下。"""
    block, records = _build(_workspace(tmp_path), "@secret.txt")
    assert records[0]["status"] == "rejected", records
    elements = _elements(block)
    assert len(elements) == 1, block
    assert elements[0].get("status") == "rejected", elements
    assert "deny 规则不允许注入" in elements[0]["#text"], elements


def test_the_over_budget_note_names_the_dropped_file_as_prose(tmp_path: Path) -> None:
    """预算注句是散文：那里的名字不许被转义。"""
    workspace = _workspace(tmp_path)
    block, records = _build(
        workspace, "@raw.txt @p&q.txt", max_total_chars=1, max_chars_per_file=40
    )
    assert [item["status"] for item in records] == ["injected", "omitted"], records
    assert "超出注入预算" in block, block
    assert AMP_FILE in block, block
    assert "&amp;" not in block, block


def test_the_count_cap_note_names_the_dropped_file_as_prose(tmp_path: Path) -> None:
    """条数注句同样是散文：第十一条被丢，名字原样出现在注句里。"""
    workspace = _workspace(tmp_path)
    plain = [f"n{k}.txt" for k in range(10)]
    for name in plain:
        (workspace / name).write_text("x\n", encoding="utf-8")
    block, _records = _build(
        workspace, " ".join([f"@{name}" for name in plain] + [f"@{AMP_FILE}"])
    )
    assert "超出单次提及条数上限" in block, block
    assert AMP_FILE in block, block
    assert "&amp;" not in block, block


def test_the_attribute_value_has_one_home() -> None:
    """三个 `path="` 拼法都过同一个转义助手，助手只有一个家。"""
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    assert source.count("def _attribute(") == 1, "转义助手没有那一个家"
    sites = [line for line in source.splitlines() if 'f\'<file path="{' in line]
    assert len(sites) == 3, sites
    for line in sites:
        assert "_attribute(" in line, line


def test_the_escaping_table_has_its_rows_in_order() -> None:
    """四个元字符各一行，且 `&` 必须排在最前：先折引号会把 `&quot;` 自己再转一遍。"""
    body = MODULE_SOURCE.read_text(encoding="utf-8").split("def _attribute(")[1]
    body = body.split("\ndef ")[0]
    positions = []
    for row in TABLE_ROWS:
        assert body.count(row) == 1, f"转义表少了这一行：{row!r}"
        positions.append(body.index(row))
    assert positions == sorted(positions), "转义表的行序被改了（& 必须最先）"
