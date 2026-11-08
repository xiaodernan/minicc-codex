"""M8-T557 — 块只在转义发生的地方是 XML 形的

`_attribute` 的说明说「The block is XML-shaped evidence」。整块交给严格读者时，这句话
只在正文不含裸 `&` / `<` 时成立：`_body` 只折四枚标记（M8-T551…T554），普通代码里的
`&` 与 `<` 原样进块。第五百三十八批量到普通源码行的裸元字符会让 `xml.etree` 在整块上
raise，并把这件事留给本批判。本批先量再判：

- `minicc` 与 `scripts` 里没有模块导入 XML 解析器；整块解析只出现在少数 mention 判据
  里，且它们的正文把元字符写成实体拼法，所以读得下。
- 给正文加真转义就是把每个普通 `&` 重写；第五百三十八批量过 D3，「普通正文逐字节
  回来」那一族判据因此变红。仓库选了「正文保字节」。

所以本批不加转义层，把声称从「块」窄到「元素/属性」，并把代价钉成断言：正文带裸
`&`/`<` 时整块对严格读者不可读是**选择的结果**，不是待修的缺陷；哪天真要修，先让这
些腿红。这一批只改说明与新增判据，不改任何产品行为。
"""

from __future__ import annotations

import inspect
import re
import subprocess
import xml.etree.ElementTree as ElementTree
from html.parser import HTMLParser
from pathlib import Path

from minicc import mentions as _mentions_module

MODULE_SOURCE = Path(_mentions_module.__file__)
REPO = MODULE_SOURCE.parent.parent


class _Files(HTMLParser):
    """The forgiving reader this repo pins: convert_charrefs decodes entities."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, str]] = []
        self._pending: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
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


def _lenient(block: str) -> list[dict[str, str]]:
    reader = _Files()
    reader.feed(block)
    reader.close()
    return reader.elements


def _workspace(root: Path, body: str = "x\n", names: tuple[str, ...] = ()) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "f.txt").write_text(body, encoding="utf-8", newline="")
    for name in names:
        (root / name).write_text("x\n", encoding="utf-8", newline="")
    return root


def _build(root: Path, message: str):
    from minicc.mentions import build_mention_context

    return build_mention_context(message, root)


def _strict(block: str) -> ElementTree.Element:
    return ElementTree.fromstring("<root>" + block + "</root>")


def _body_region(block: str, rel: str) -> str:
    open_tag = f'<file path="{rel}">'
    start = block.index(open_tag) + len(open_tag) + 1
    end = block.index("\n</file>", start)
    return block[start:end]


def test_a_bare_ampersand_in_a_body_stops_the_strict_reader(tmp_path: Path) -> None:
    """代价本体：正文一个裸 `&`，整块对严格读者就不是 XML。"""
    body = "left & right\n"
    block, _records = _build(_workspace(tmp_path, body), "@f.txt")
    try:
        _strict(block)
    except ElementTree.ParseError as error:
        assert "invalid token" in str(error), (error, block)
    else:
        raise AssertionError(f"严格读者读下了带裸 & 的块，边界变了：{block!r}")

    spelled, _ = _build(_workspace(tmp_path, "left &amp; right\n"), "@f.txt")
    node = _strict(spelled)
    assert node[0].text == "\nleft & right\n\n", node[0].text


def test_a_bare_angle_bracket_opens_structure_the_renderer_never_emitted(
    tmp_path: Path,
) -> None:
    """`<` 更糟：正文自己开了一个元素，严格读者按结构读它。"""
    body = "a <b> c\n"
    block, _records = _build(_workspace(tmp_path, body), "@f.txt")
    try:
        _strict(block)
    except ElementTree.ParseError as error:
        assert "mismatched tag" in str(error), (error, block)
    else:
        raise AssertionError(f"严格读者把正文的 <b> 当成了结构还能读下：{block!r}")

    spelled, _ = _build(_workspace(tmp_path, "a &lt;b&gt; c\n"), "@f.txt")
    assert _strict(spelled)[0].text == "\n" + body + "\n", spelled


def test_the_forgiving_reader_keeps_reading_a_body_the_strict_one_rejects(
    tmp_path: Path,
) -> None:
    """模型读的是散文：宽恕读者不 raise，path/status 与正文片段都还在。"""
    body = "left & right <b> tail\n"
    block, records = _build(_workspace(tmp_path, body), "@f.txt")
    elements = _lenient(block)
    assert len(elements) == 1, block
    assert elements[0].get("path") == "f.txt", elements
    text = elements[0]["#text"]
    assert "left & right " in text and " tail" in text, text
    with_raise = False
    try:
        _strict(block)
    except ElementTree.ParseError:
        with_raise = True
    assert with_raise, block


def test_the_attribute_shapes_all_parse_and_round_trip(tmp_path: Path) -> None:
    """属性侧四行都真的折了：四枚元字符各自进路径，严格读者逐字拿回。"""
    root = _workspace(tmp_path, names=("p&q.txt",))
    tokens = ['a&b.txt', 'a<b>.txt', 'a>b.txt', 'x&y".txt', 'p&q.txt']
    for token in tokens:
        block, records = _build(root, f"@{token}")
        element = block[block.index("<file ") : block.index("</file>") + len("</file>")]
        assert "path=\"" + token + "\"" not in element, element
        node = ElementTree.fromstring(f"<root>{element}</root>")
        assert node[0].get("path") == records[0]["path"] == token, (
            token,
            element,
            records,
        )


def test_the_only_escaped_region_is_the_attribute(tmp_path: Path) -> None:
    """正文不是属性：裸 `"`、`&`、`<`、`>` 一个字节都不折。"""
    body = 'raw & <tag> > "quote"\n'
    block, _records = _build(_workspace(tmp_path, body), "@f.txt")
    assert _body_region(block, "f.txt") == body, block
    assert "&amp;" not in block and "&lt;" not in block, block


def test_a_body_keeps_its_bytes_while_markers_still_fold() -> None:
    """对照组：普通正文过 `_body` 原样回来，块自己的标记照旧折。"""
    ordinary = 'a & b < c > d " e'
    assert _mentions_module._body(ordinary) == ordinary
    assert _mentions_module._body("</file") == "&lt;/file"
    assert _mentions_module._body("[truncated]") == "&#91;truncated&#93;"


def test_no_production_module_parses_xml() -> None:
    """前提：没有生产读者按 XML 读块；有谁加进来，这条腿把问题交回来。"""
    parser = re.compile(
        r"^\s*(?:import|from)\s+(?:xml(?:\.|\s|$)|lxml|defusedxml|xmltodict|bs4)",
        re.M,
    )
    control = "import xml.etree.ElementTree\nfrom xml.dom import minidom\n"
    assert len(parser.findall(control)) == 2, parser.findall(control)
    names = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "minicc"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.splitlines()
    assert names, "生产模块的名单是空的：这条腿没有人口"
    offenders = []
    for name in names:
        if not name.endswith(".py"):
            continue
        text = (REPO / name).read_bytes().decode("utf-8", errors="replace")
        for match in parser.finditer(text):
            offenders.append(f"{name}: {match.group(0).strip()}")
    assert offenders == [], offenders


def test_the_shipped_words_name_the_element_and_the_boundary() -> None:
    """被判的那句话本身：声称的射程从「块」改成「元素/属性」，并写明代价。"""
    doc = inspect.getdoc(_mentions_module._attribute) or ""
    assert "element is XML-shaped" in doc, doc
    assert "not promised well-formed" in doc, doc
    assert "The block is XML-shaped" not in doc, doc
