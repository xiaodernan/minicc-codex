"""M8-T262: a clipped raw record must name the bytes its own ceiling dropped.

Measured on the pre-fix tree by read-only probes (real handlers in-process, real CLI
record reopened from disk, ceilings read off the shipped source by AST):

    shipped ceilings passed to record_text():      minicc/main.py:109 = 6000,
                                                   minicc/web.py:1498 / :1988 = 8000
    memory_list with the default limit=20:         render() = 11 295 chars
    -> stored at 6000, the record dropped 5 295   -> the stored text contained 「5295」 0 times
    todo_read at MAX_TODOS x MAX_CONTENT_CHARS:    render() = 28 977 -> stored 6000
    web_search at max_results=8 with parser caps:  render() = 23 676 -> stored 6000 (2 of 8 URLs survive)
    the same call on a typical page:               render() =  1 474 -> stored 1 474 (untouched)

``record_text`` is the only clip in this family that does not say what it did.  The
observation clip (``minicc/agent/loop.py:336``) appends 「…」, the structured-data clip
(``minicc/agent/loop.py:340``) rewrites the payload with ``"truncated": True``, and
``_public_data`` (``minicc/agent/loop.py:306``) prints 「其余 N 项已省略」.  A record that
went through ``[:ceiling]`` carries neither: the last line is a half-sentence of filler,
and ``minicc/web.py:1505`` still writes ``"truncated": bool(result.truncated)`` - false,
because the handler never truncated - beside a body that lost 48% of itself.  The model
side is unbounded (``minicc/agent/loop.py:599``, ``:1171`` send ``render()`` verbatim), so
the record is a strictly lossier copy of what was already sent, silently.

The fix composes a sentence inside the ceiling: ``kept = ceiling - len(notice)``, solved by
fixed-point iteration because the sentence prints ``kept`` itself, so ``kept + dropped ==
total`` and ``len(stored) == ceiling`` hold at the same time (M8-T244's length pin stays).
``min(ceilings)`` is pinned to leave room for the sentence, and the too-thin ceiling that
cannot hold it keeps today's bare prefix as a named boundary.  ``render()`` - the bytes the
model sees - and the ``truncated`` field are untouched, each by its own case.

C6 drives the real memory handler through the real CLI record and reopens it; C7 drives
the real web handler on a real parser run.  C4/C5/C10 reconcile the sentence against the
shipped source, each with a floor, so an empty census cannot be reported as a clean one.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import minicc.tools.memory as memory_module
import minicc.tools.schemas as schemas_module
import minicc.tools.web as web_module
from minicc.main import CliView
from minicc.session import SessionStore
from minicc.tools.memory import DEFAULT_LIST_LIMIT, MAX_MEMORY_CHARS, MemoryTools
from minicc.tools.schemas import (
    HEAD_CHARS,
    TAIL_CHARS,
    TRUNCATION_MARKER,
    ToolCall,
    ToolResult,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MINICC = REPO_ROOT / "minicc"
SCHEMAS_MODULE = MINICC / "tools" / "schemas.py"

#: The three numbers the clip is made of, in the order the sentence has to print them.
NUMBER_NAMES = ("kept", "dropped", "total")

#: Floors for the C4 census, each far below the population measured in this repository,
#: so a floor only fires when its own census went blind - and the message says which one.
MIN_MINICC_MODULES = 20
MIN_MINICC_STRING_CONSTANTS = 200

#: The charged spelling.  Only ``schemas.py`` may compose it.
CLIP_WORD = "记录截断"

#: A ceiling no sentence can stand on.  C11 pins what the record does there; C10 pins
#: that no shipped ceiling ever gets this thin.
THIN_CEILING = 8


def _grading_this_plane() -> None:
    """The censuses read files off disk; they must be the files this run imported."""
    for module, expected in (
        (schemas_module, SCHEMAS_MODULE),
        (web_module, MINICC / "tools" / "web.py"),
        (memory_module, MINICC / "tools" / "memory.py"),
    ):
        resolved = Path(module.__file__).resolve()
        assert resolved == expected, (
            f"this file grades {expected} but the import resolved to {resolved} - the census would "
            "clear a copy that is not the one in use"
        )


def _raw(width: int) -> ToolResult:
    """A body travelling the raw ``output`` channel, with no summary to shift its width."""
    return ToolResult(status="ok", output="字" * width)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _minicc_trees() -> list[tuple[Path, ast.Module]]:
    trees = [(path, _tree(path)) for path in sorted(MINICC.rglob("*.py"))]
    assert len(trees) >= MIN_MINICC_MODULES, (
        f"walking {MINICC} found only {len(trees)} modules - the census read too little to clear anything"
    )
    return trees


def _ceilings() -> list[int]:
    """Every literal ceiling minicc passes to ``record_text``."""
    found: list[int] = []
    for path, tree in _minicc_trees():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "record_text"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, int)
            ):
                found.append(int(node.args[0].value))
    assert found, f"no literal ceiling reaches record_text() under {MINICC}; the record surfaces are unbounded"
    return sorted(set(found))


def _notice_pattern() -> tuple[re.Pattern[str], list[str]]:
    """A reader for the sentence, built from the shipped template - never a copy of it."""
    template = schemas_module.RECORD_CLIP_NOTICE
    names = re.findall(r"\{(kept|dropped|total)\}", template)
    assert len(set(names)) == len(names) == len(NUMBER_NAMES) and sorted(names) == sorted(NUMBER_NAMES), (
        f"the shipped template prints {names}; this file reads {NUMBER_NAMES} - one sentence, one reader"
    )
    pieces = re.split(r"\{(kept|dropped|total)\}", template)
    body = "".join(re.escape(piece) if index % 2 == 0 else r"(\d+)" for index, piece in enumerate(pieces))
    return re.compile(body), names


def _read_notice(stored: str) -> tuple[dict[str, int], str]:
    pattern, names = _notice_pattern()
    match = pattern.search(stored)
    assert match, (
        f"no sentence built from {schemas_module.RECORD_CLIP_NOTICE!r} appears in the stored record: "
        f"{stored[-200:]!r}"
    )
    return dict(zip(names, (int(group) for group in match.groups()))), match.group(0)


def _stored_cli_record(tmp_path: Path, call: ToolCall, result: ToolResult, name: str) -> str:
    """Drive the real CLI record path and return what the reopened session holds."""
    view = CliView(SessionStore(tmp_path, name))
    view.record_tool(call, result)
    reopened = CliView(SessionStore(tmp_path, name), announce_resume=True)
    return reopened.tool_history[-1]["output"]


def _search_results(title_pad: int, url_pad: int, snippet_pad: int, query: str) -> ToolResult:
    """Real parser, real handler: the cache seam is the shipped way to feed a page without network."""
    parts = ["<html><body>"]
    for index in range(web_module.MAX_RESULTS):
        title = "标题%02d " % index + "字" * title_pad
        url = "https://%s%d.example.com/%s?q=%d" % (query[:1], index, "u" * url_pad, index)
        snippet = "摘要%02d " % index + "内容" * snippet_pad
        parts.append(
            '<div class="result"><h2><a class="result-link" href="%s">%s</a></h2>'
            '<td class="result-snippet">%s</td></div>' % (url, title, snippet)
        )
    parts.append("</body></html>")
    results = web_module.parse_search_html("".join(parts), web_module.MAX_RESULTS)
    assert len(results) == web_module.MAX_RESULTS, (
        f"the parser kept {len(results)} of {web_module.MAX_RESULTS} fake results - the fixture shape, "
        "not the clip, is what this measures"
    )
    fetch = web_module._SearchFetch(source="DuckDuckGo HTML", results=results, diagnostics=[], html="")
    original = web_module._fetch_search
    web_module._fetch_search = lambda _query, captured=fetch: captured
    try:
        return web_module.web_search({"query": query, "max_results": web_module.MAX_RESULTS})
    finally:
        web_module._fetch_search = original


# --- C1: the clip must carry its own arithmetic --------------------------------------


def test_a_clipped_raw_record_names_the_bytes_it_dropped(tmp_path: Path) -> None:
    _grading_this_plane()
    ceiling = min(_ceilings())
    result = _raw(ceiling + ceiling // 2 + 7)
    rendered = result.render()
    assert len(rendered) > ceiling, f"fixture is {len(rendered)} chars, not wider than the ceiling {ceiling}"
    stored = _stored_cli_record(tmp_path, ToolCall(tool="bash", arguments={"command": "echo long"}), result, "clip-raw")
    assert CLIP_WORD in stored, (
        f"a {len(rendered)}-char body was stored as {len(stored)} chars and the record says nothing about it; "
        f"the tail of the stored text is {stored[-90:]!r}"
    )
    numbers, notice = _read_notice(stored)
    assert len(stored) == ceiling, f"the sentence plus the kept bytes are {len(stored)}, the ceiling is {ceiling}"
    assert numbers["total"] == len(rendered), (
        f"the record claims a complete output of {numbers['total']} chars while the same result renders "
        f"{len(rendered)}"
    )
    assert numbers["kept"] + numbers["dropped"] == numbers["total"], (
        f"the sentence prints kept={numbers['kept']} + dropped={numbers['dropped']} for a total of "
        f"{numbers['total']} - the bytes do not add up"
    )
    assert numbers["kept"] + len(notice) == ceiling, (
        f"kept={numbers['kept']} plus a {len(notice)}-char sentence is {numbers['kept'] + len(notice)} chars, "
        f"not the ceiling {ceiling} this record was cut to"
    )
    assert stored[: numbers["kept"]] == rendered[: numbers["kept"]], "the record keeps fewer bytes than it claims"
    assert TRUNCATION_MARKER not in stored, (
        "the raw channel borrowed the head/tail marker, which promises a tail this record does not hold"
    )


# --- C2: a record that fits stays byte for byte --------------------------------------


def test_a_record_that_fits_is_byte_identical_to_render(tmp_path: Path) -> None:
    _grading_this_plane()
    ceiling = min(_ceilings())
    for width in (1, ceiling // 3, ceiling - 1, ceiling):
        result = _raw(width)
        rendered = result.render()
        assert len(rendered) == width, f"a {width}-char body rendered as {len(rendered)} chars - the fixture is not what this case measures"
        stored = _stored_cli_record(tmp_path, ToolCall(tool="bash", arguments={"command": "echo fit"}), result, f"fit-{width}")
        assert stored == rendered, f"a {width}-char body at ceiling {ceiling} was not stored verbatim"
        assert CLIP_WORD not in stored, (
            f"a record that lost nothing gained a clip sentence anyway: {stored[-120:]!r}"
        )


# --- C3: the budgeted channel keeps M8-T244's promise --------------------------------


def test_the_head_channel_record_gains_no_clip_notice() -> None:
    _grading_this_plane()
    ceiling = min(_ceilings())
    result = ToolResult(
        status="ok",
        summary="MCP srv/big",
        head="H" * HEAD_CHARS,
        tail="T" * TAIL_CHARS,
        truncated=True,
    )
    rendered = result.render()
    assert len(rendered) > ceiling, f"the composition is {len(rendered)} chars, below the ceiling {ceiling}"
    stored = result.record_text(ceiling)
    assert stored == rendered, "the head/tail channel was re-cut; M8-T244 promised the tail the marker advertises"
    assert stored.count(TRUNCATION_MARKER) == rendered.count(TRUNCATION_MARKER) == 1, (
        "the budget marker no longer survives the record exactly once"
    )
    assert CLIP_WORD not in stored, f"the budgeted body was given a second truncation sentence: {stored[-160:]!r}"


# --- C4: one author for the sentence --------------------------------------------------


def test_the_clip_sentence_has_exactly_one_author_in_minicc() -> None:
    _grading_this_plane()
    trees = _minicc_trees()
    constants = [
        node.value
        for _, tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert len(constants) >= MIN_MINICC_STRING_CONSTANTS, (
        f"the walk read {len(constants)} string constants out of {len(trees)} modules - below the floor "
        f"{MIN_MINICC_STRING_CONSTANTS}, so its silence about {CLIP_WORD!r} is not evidence"
    )
    authors = sorted(
        {str(path.relative_to(REPO_ROOT)) for path, tree in trees
         for node in ast.walk(tree)
         if isinstance(node, ast.Constant) and isinstance(node.value, str) and CLIP_WORD in node.value}
    )
    assert authors and authors == [str(SCHEMAS_MODULE.relative_to(REPO_ROOT))], (
        f"the clip sentence is composed by {authors}; only schemas.py may word what the record says about itself - "
        "a second copy can drift and nothing would reconcile them"
    )


# --- C5: the arithmetic at every shipped ceiling -------------------------------------


def test_the_notice_reconciles_at_every_shipped_ceiling_and_width() -> None:
    _grading_this_plane()
    widths_checked = 0
    for ceiling in _ceilings():
        widths = {1, ceiling // 2, ceiling - 1, ceiling, ceiling + 1, ceiling + 2, ceiling * 20}
        for digits in range(1, len(str(ceiling * 20)) + 1):
            base = 10 ** digits
            widths |= {base - 1, base, base + 1}
        for width in sorted(widths):
            result = _raw(width)
            stored = result.record_text(ceiling)
            rendered = result.render()
            if width <= ceiling:
                assert stored == rendered, f"a {width}-char body at ceiling {ceiling} was clipped anyway"
                assert CLIP_WORD not in stored
                continue
            widths_checked += 1
            assert len(stored) == ceiling, (
                f"ceiling {ceiling}, body {width}: stored {len(stored)} chars"
            )
            assert CLIP_WORD in stored, f"ceiling {ceiling}, body {width}: the clip stayed silent"
            numbers, notice = _read_notice(stored)
            assert numbers == {
                "kept": ceiling - len(notice),
                "dropped": width - (ceiling - len(notice)),
                "total": width,
            }, f"ceiling {ceiling}, body {width}: the sentence reads {numbers} against a {len(notice)}-char tail"
            assert stored[: numbers["kept"]] == rendered[: numbers["kept"]], (
                f"ceiling {ceiling}, body {width}: the {numbers['kept']} bytes the sentence counts are not the prefix"
            )
        assert widths_checked, "no width above any shipped ceiling was measured - the census read nothing"


# --- C6: the shipped record of a real, default-shaped call ---------------------------


def test_the_shipped_cli_record_of_a_real_memory_list_says_it_was_clipped(tmp_path: Path) -> None:
    _grading_this_plane()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = MemoryTools(workspace)
    for index in range(DEFAULT_LIST_LIMIT):
        filler = "记" * (MAX_MEMORY_CHARS - 5)
        tools.write({"content": f"记忆{index:02d} {filler}", "scope": "project", "source": f"t262-{index:02d}"})
    result = tools.list_entries({"scope": "project"})
    rendered = result.render()
    ceiling = min(_ceilings())
    assert len(rendered) > ceiling, (
        f"the default-shaped memory_list renders {len(rendered)} chars, at or under the shipped ceiling "
        f"{ceiling}; this case needs a body the record really has to cut"
    )
    listed = result.data["entries"]
    assert len(listed) == DEFAULT_LIST_LIMIT, f"the handler listed {len(listed)} of {DEFAULT_LIST_LIMIT} entries"
    stored = _stored_cli_record(tmp_path, ToolCall(tool="memory_list", arguments={"scope": "project"}), result, "memory-clip")
    numbers, notice = _read_notice(stored)
    assert numbers["total"] == len(rendered)
    assert numbers["kept"] + len(notice) == ceiling and len(stored) == ceiling
    assert stored[numbers["kept"] :] == notice, "the sentence is not what the record ends with"
    dropped_entry = listed[-1]
    assert dropped_entry["id"] not in stored, (
        f"the record still holds the entry {dropped_entry['id']} it says it dropped"
    )
    assert listed[0]["id"] in stored, "not even the newest entry survived the shipped ceiling - fixture or clip?"


# --- C7: a production-shaped record that fits stays untouched ------------------------


def test_a_typical_web_search_record_still_gains_no_notice() -> None:
    _grading_this_plane()
    result = _search_results(6, 35, 45, "typical-page")
    rendered = result.render()
    ceiling = min(_ceilings())
    assert len(rendered) < ceiling, (
        f"the typical page renders {len(rendered)} chars, over the shipped ceiling {ceiling}; "
        "this case exists to prove the clip does not fire when nothing is dropped"
    )
    for shipped in _ceilings():
        stored = result.record_text(shipped)
        assert stored == rendered, f"a typical {len(rendered)}-char search body was clipped at ceiling {shipped}"
        assert CLIP_WORD not in stored, f"the record of a page that fit announces a clip: {stored[-120:]!r}"


# --- C8: the clip only touches the stored text ---------------------------------------


def test_record_text_leaves_the_handlers_fields_alone() -> None:
    _grading_this_plane()
    ceiling = min(_ceilings())
    result = ToolResult(status="ok", summary="raw", output="字" * (ceiling + ceiling // 2), security_tags=["untrusted"])
    before = (result.status, result.summary, result.output, result.head, result.tail, result.truncated)
    stored = result.record_text(ceiling)
    after = (result.status, result.summary, result.output, result.head, result.tail, result.truncated)
    assert len(stored) < len(result.output), "the fixture did not reach the clip, so it cannot witness this field"
    assert before == after, f"record_text mutated the handler's own fields: {before} -> {after}"
    assert result.truncated is False, (
        "the clip set truncated=True; that field reports what the *handler* did to its output "
        "(minicc/web.py:1505 prints it as a badge) and must keep meaning that"
    )
    assert result.to_dict()["truncated"] is False, "the mutated flag reached the serialised event"


# --- C9: the model-facing bytes are not the record's --------------------------------


def test_the_clip_does_not_change_what_the_model_sees() -> None:
    _grading_this_plane()
    ceiling = min(_ceilings())
    result = _raw(ceiling + ceiling // 2)
    before = result.render()
    stored = result.record_text(ceiling)
    after = result.render()
    assert after == before, "render() changed after record_text(); the model now sees the record's bytes"
    assert CLIP_WORD not in before, (
        "the clip sentence lives in render(); the record and the model would read different texts"
    )
    assert len(after) > len(stored), f"nothing was clipped ({len(after)} vs {len(stored)}), so this proves nothing"


# --- C10: a shipped ceiling always leaves room for the sentence ----------------------


def test_every_shipped_ceiling_leaves_room_for_the_sentence() -> None:
    _grading_this_plane()
    narrowest = schemas_module.RECORD_CLIP_NOTICE.format(kept=0, dropped=0, total=0)
    assert THIN_CEILING < len(narrowest), (
        f"the boundary C11 pins (THIN_CEILING={THIN_CEILING}) has to be thinner than the narrowest "
        f"sentence the clip can print ({len(narrowest)} chars), or C11 measures nothing"
    )
    for ceiling in _ceilings():
        assert len(narrowest) < ceiling, (
            f"the sentence is {len(narrowest)} chars on its own and the shipped ceiling is {ceiling}; "
            "record_text would fall back to the silent prefix for every real body"
        )
        stored = _raw(ceiling + 1).record_text(ceiling)
        assert CLIP_WORD in stored, (
            f"at ceiling {ceiling} a body one char too wide already lost the sentence: {stored[-80:]!r}"
        )


# --- C11: the named boundary where the sentence cannot stand -------------------------


def test_a_ceiling_too_thin_for_the_sentence_keeps_the_bare_prefix() -> None:
    _grading_this_plane()
    text = "字" * (THIN_CEILING + 10)
    stored = ToolResult(status="ok", output=text).record_text(THIN_CEILING)
    assert stored == text[:THIN_CEILING], (
        f"a ceiling of {THIN_CEILING} chars cannot hold any clip sentence this file knows of; the fallback is "
        f"the bare prefix, and it produced {stored!r} instead"
    )
    assert len(stored) == THIN_CEILING and stored, "the fallback swallowed the record instead of shortening it"
