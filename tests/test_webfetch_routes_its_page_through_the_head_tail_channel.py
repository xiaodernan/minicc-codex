"""M8-T259: a truncated web page must travel the channel ``record_text`` clips by.

``minicc/tools/webfetch.py`` splits its page with the shipped ``split_output`` and then folds
the pieces, a hand-copied truncation sentence, and the untrusted-data note into the raw
``output`` channel while handing back ``head=""``.  Every other splitter in the tree
(``mcp.py``, ``bash.py``, ``fs.py``, ``git.py``) returns the slices in the ``head``/``tail``
fields, which is exactly the field ``ToolResult.record_text`` looks at to decide that a body
is already inside the shipped budget and must not be cut further.  So the CLI's store clip
silently drops tail bytes - and the warning line that tells the reader the body is untrusted -
from a record that still prints 「保留头 2000 + 尾 4000 字符」.

Nothing here hard-codes a number, a sentence, or a ceiling that production owns: the budget
comes from ``HEAD_CHARS``/``TAIL_CHARS``, the marker from ``TRUNCATION_MARKER``, the note from
``webfetch``'s own source, the ceilings from AST readings of ``main.py``/``web.py``.
"""

from __future__ import annotations

import ast
import contextlib
import io
import re
from pathlib import Path

import pytest

import minicc
from minicc.main import CliView
from minicc.session import SessionStore
# ``minicc.tools`` re-exports the webfetch *handler* under the name ``webfetch``, so the
# submodule cannot be reached as an attribute of the package; import the two names directly.
from minicc.tools.registry import split_output
from minicc.tools.schemas import HEAD_CHARS, TAIL_CHARS, TRUNCATION_MARKER, ToolCall, ToolResult
from minicc.tools.webfetch import MAX_BYTES_DEFAULT, build_tool_result

REPO_ROOT = Path(__file__).resolve().parents[1]
MINICC = REPO_ROOT / "minicc"
SCHEMAS = MINICC / "tools" / "schemas.py"
WEBFETCH = MINICC / "tools" / "webfetch.py"
MAIN_PY = MINICC / "main.py"
WEB_PY = MINICC / "web.py"

URL = "http://127.0.0.1/probe"
TITLE = "probe page"

#: the words every truncation sentence promises with numbers; a file that composes this
#: shape outside ``schemas.py`` is writing a second copy of a budget it does not own.
PROMISE_MARKERS = ("保留头", "尾", "字符")


def _grading_this_plane() -> None:
    resolved = Path(minicc.__file__).resolve()
    assert resolved.is_relative_to(REPO_ROOT), f"grading a different tree: {resolved}"


def _fetch(text: str, *, page_truncated: bool = False) -> ToolResult:
    """Shape a fetch through the production builder; no socket is opened."""
    return build_tool_result(
        {
            "status": 200,
            "content_type": "text/html",
            "title": TITLE,
            "text": text,
            "truncated": page_truncated,
            "url": URL,
            "final_url": URL,
            "bytes": len(text),
        }
    )


def _over_budget_page() -> str:
    return "H" * HEAD_CHARS + "M" * 1000 + "T" * TAIL_CHARS


def _untrusted_note() -> str:
    """The note webfetch itself writes, read out of its source - not copied into here."""
    tree = ast.parse(WEBFETCH.read_text(encoding="utf-8"))
    found = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "不可信" in node.value
    }
    assert len(found) == 1, (
        f"webfetch must write exactly one untrusted-data note for this door to look for; "
        f"found {len(found)} in {WEBFETCH.name}")
    return next(iter(found))


def _record_ceilings(module: Path) -> list[int]:
    """Every literal ceiling passed to ``record_text`` in ``module``, from one AST walk."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    ceilings = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "record_text"
        ):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                    ceilings.append(arg.value)
    return ceilings


# --- C1: the record a user reopens must hold the note and the bytes its text promises ---


def test_a_stored_truncated_page_keeps_the_note_and_the_promised_tail(
    tmp_path: Path,
) -> None:
    _grading_this_plane()
    note = _untrusted_note()
    body = _over_budget_page()
    result = _fetch(body)
    head_slice, tail_slice, cut = split_output(body)
    assert cut, "the fixture must be wider than the shipped head+tail budget"

    view = CliView(SessionStore(tmp_path, "webfetch-record"))
    view.record_tool(ToolCall(tool="webfetch", arguments={"url": URL}, call_id="c1"), result)
    again = CliView(SessionStore(tmp_path, "webfetch-record"), announce_resume=True)
    stored = again.tool_history[-1]["output"]

    assert TRUNCATION_MARKER in stored, (
        f"the stored record carries no truncation marker at all, so the page reads as complete:\n"
        f"{stored[:200]!r}")
    assert head_slice in stored and tail_slice in stored, (
        f"the stored record prints 「{TRUNCATION_MARKER}」 yet only "
        f"{sum(1 for ch in stored if ch == 'H')}/{HEAD_CHARS} head bytes and "
        f"{sum(1 for ch in stored if ch == 'T')}/{TAIL_CHARS} tail bytes of the page survive")
    assert stored.rstrip().endswith(note), (
        f"the untrusted-data note is the last line of a webfetch body, so it is the first thing "
        f"a clip removes; stored ends with {stored[-60:]!r}")

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        again.expand()
    printed = buffer.getvalue()
    assert note in printed and tail_slice in printed, (
        f"/expand reprints {len(printed)} chars without "
        f"{'the note' if note not in printed else 'the promised tail'} - what the user reopens is "
        f"untrusted page text with no warning on it")


# --- C2: the page must travel the channel record_text knows about ----------------------


def test_the_page_body_travels_the_head_tail_channel() -> None:
    _grading_this_plane()
    note = _untrusted_note()
    result = _fetch(_over_budget_page())
    assert result.head and result.tail, (
        f"webfetch split its page but returned head={result.head[:24]!r} tail={result.tail[:24]!r}; "
        f"record_text only trusts a body that came through those fields")
    assert not result.output, (
        f"the page is carried twice - once in head/tail and once in output "
        f"({len(result.output)} chars) - so the raw-channel clip applies to a body that is "
        f"already inside the budget")
    assert result.tail.endswith(note)
    assert URL in result.head and TITLE in result.head, (
        "the provenance lines belong with the body; dropping them would leave the reader no "
        "way back to the source")


# --- C3: the summary line is the model's only view of the summary ----------------------


def test_the_summary_reaches_the_model_exactly_once() -> None:
    _grading_this_plane()
    result = _fetch(_over_budget_page())
    rendered = result.render()
    times = rendered.count(result.summary)
    assert times == 1, (
        f"render() prepends the summary and webfetch also put it inside the body, so the model "
        f"pays for it {times} times: {result.summary[:60]!r}")


# --- C4: one sentence, one owner -------------------------------------------------------


def _promise_sentence_sites() -> list[tuple[str, int]]:
    """Every place in minicc/ that composes a sentence naming the head/tail budget.

    One f-string is walked as the JoinedStr *and* as the Constant inside it, so the same
    sentence would otherwise be charged several times; unique (file, line) is one site.
    """
    seen: set[tuple[str, int]] = set()
    for path in sorted(MINICC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.JoinedStr, ast.Constant, ast.BinOp)):
                continue
            text = ast.get_source_segment(source, node) or ""
            if len(text) > 200 or not all(marker in text for marker in PROMISE_MARKERS):
                continue
            if "输出已截断" not in text:
                continue
            seen.add((str(path.relative_to(REPO_ROOT)), node.lineno))
    return sorted(seen)


def test_only_schemas_composes_the_sentence_that_promises_the_budget() -> None:
    _grading_this_plane()
    sites = _promise_sentence_sites()
    assert sites, (
        "the scan found no sentence naming the head/tail budget anywhere under minicc/ - "
        "that means it read nothing, not that the promise is written in one place")
    owner = str(SCHEMAS.relative_to(REPO_ROOT))
    extra = [site for site in sites if site[0] != owner]
    assert not extra, (
        f"{owner} owns 「{TRUNCATION_MARKER}」; these sites re-type it and will drift: {extra}")


# --- C5: the model-facing bytes are the shipped composition, written once --------------


def _expected_render(result: ToolResult, body: str, note: str) -> str:
    """The render() contract, expressed with production's own splitter and marker."""
    head_slice, tail_slice, cut = split_output(body)
    prefix = f"来源: {URL}\n标题: {TITLE}"
    if cut:
        return f"{result.summary}\n{prefix}\n\n{head_slice}\n\n{TRUNCATION_MARKER}\n\n" \
               f"{tail_slice}\n\n{note}"
    return f"{result.summary}\n{prefix}\n\n{body}\n\n{note}"


@pytest.mark.parametrize("size", [0, 12, HEAD_CHARS, HEAD_CHARS + TAIL_CHARS, HEAD_CHARS + TAIL_CHARS + 1])
def test_the_page_arrives_as_the_derived_composition(size: int) -> None:
    _grading_this_plane()
    note = _untrusted_note()
    body = "".join(str(index % 10) for index in range(size))
    result = _fetch(body)
    expected = _expected_render(result, body, note)
    assert result.render() == expected, (
        f"for a {size}-char page the model-facing text is not the shipped composition of "
        f"summary + provenance + body + note: {result.render()[:120]!r}")
    if size > HEAD_CHARS + TAIL_CHARS:
        # The promise sentence names the *page's* first and last bytes, so the door checks
        # them itself: an expectation built only out of split_output() would follow that
        # function even if it started shipping the head twice.
        rendered = result.render()
        assert body[:HEAD_CHARS] in rendered and body[-TAIL_CHARS:] in rendered, (
            f"a {size}-char page is promised as first {HEAD_CHARS} + last {TAIL_CHARS} chars; "
            f"the shipped text carries "
            f"head-from-start={body[:HEAD_CHARS] in rendered}, "
            f"tail-from-end={body[-TAIL_CHARS:] in rendered}")


# --- C6: the web card's ceiling must not be the one that bites either ------------------


def test_the_web_card_record_keeps_the_note_too() -> None:
    _grading_this_plane()
    note = _untrusted_note()
    ceilings = _record_ceilings(WEB_PY)
    assert ceilings, f"no record_text ceiling could be read out of {WEB_PY.name} - the scan read nothing"
    ceiling = min(ceilings)
    result = _fetch(_over_budget_page())
    stored = result.record_text(ceiling)
    tail_slice = result.tail[-TAIL_CHARS:] if result.tail else ""
    assert note in stored and (not tail_slice or tail_slice in stored), (
        f"the web card stores {len(stored)} of a {len(result.render())} char record at ceiling "
        f"{ceiling}: note present={note in stored}")


# --- C7: a page cut by the byte cap still says so in the summary -----------------------


def test_the_page_level_byte_cap_is_named_in_the_summary_with_its_own_number() -> None:
    _grading_this_plane()
    summary = _fetch("tiny page", page_truncated=True).summary
    match = re.search(r"页面超过 (\d+)KB 已截断", summary)
    assert match, f"a page cut at the fetch cap is not named in the summary: {summary!r}"
    declared = int(match.group(1))
    assert declared == MAX_BYTES_DEFAULT // 1024, (
        f"the summary says {declared}KB while the fetcher's own cap is "
        f"{MAX_BYTES_DEFAULT} bytes ({MAX_BYTES_DEFAULT // 1024}KB)")


# --- C8: the sentence that names the tail budget must never print without a tail -------

def test_a_page_capped_by_bytes_that_fits_the_budget_prints_no_unshipped_promise() -> None:
    """The two truncations are different facts and only one of them has a tail to ship.

    ``_download`` caps the payload at ``MAX_BYTES_DEFAULT``; ``split_output`` caps the
    *rendered* text at head+tail.  A page can lose bytes to the first and still fit inside
    the second, and then it has no tail slice at all.  ``truncated`` must stay true (the
    fetch really did drop bytes - that is the completeness badge the web card reads), but
    the head/tail sentence has nothing to promise, and printing it is the same lie C1
    measures from the other side.
    """
    _grading_this_plane()
    body = "x" * (HEAD_CHARS + TAIL_CHARS)
    result = _fetch(body, page_truncated=True)
    assert result.truncated, (
        "the fetch dropped bytes at the page cap, so the record must keep saying so")
    assert not result.tail, (
        f"a page whose text is inside the budget has no tail slice, got {result.tail[:40]!r}")
    rendered = result.render()
    assert TRUNCATION_MARKER not in rendered, (
        f"render() printed 「{TRUNCATION_MARKER}」 with no tail after it - the sentence names "
        f"a {TAIL_CHARS}-char tail this page never needed:\n{rendered[-160:]!r}")
    assert body in rendered, "every text byte the fetcher received must reach the model"
    assert "页面超过" in result.summary, "the cap that really did bite must still be disclosed"
