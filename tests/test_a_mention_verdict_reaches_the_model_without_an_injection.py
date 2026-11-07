"""M8-T548 + M8-T549 — 提及的判决要进块，块非空的唯一理由不该是「恰好有个文件被注入了」

`minicc/mentions.py` 的渲染器按「有没有注入」分岔（第五百三十一批之后的字节，
`:301-328`）：注入分支把 `rejected` / `missing` / `binary` 三种判决都标注进块，
零注入分支只标注 `rejected`，其余落到 `return "", records`。于是 `@nosuch`、
`@binaryfile` 两条消息给模型的是**空块**，而 `@ok.py @nosuch @binaryfile` 把两条
都写了出来（第五百三十一批 §2-2 实测）。M8-T329 给「超出条数上限」那条通道补的
正是这一形：静默丢掉读起来像从没写过。一条 `missing` 判决对模型来说就是「这个文件
我没读到」那句话本身，它掉在块外，模型只剩下猜。

同一片地方还有两个手抄的家：被拒标注那句 f-string 在 `:306`（注入分支）与 `:319`
（零注入分支）各拼一遍——第五百三十一批的臂 A7 就被这个骗过一次（针只钉了一处，
九腿全绿）；「超出注入预算」那句也有两个家，而且**两句给读者的补救不一样**：
`:311` 说「可用 read_file 读取」，`:324` 只说「未包含内容」。读者能不能得到补救，
取决于有没有别的文件恰好被注入了。

本批改机制：标注行只构造一次，块非空 ⟺ 这条消息里有判决要说；空块 ⟺ 没有 @-提及。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from minicc import mentions as _mentions_module
from minicc.mentions import (
    apply_mentions,
    build_mention_context,
    extract_mention_tokens,
)

# 扫描的对象必须是**这些腿真正在跑的那一个模块**的字节：从 ``__file__`` 现推，
# 不从 ``__file__`` 的祖父目录拼路径（那会把「判据文件住在哪儿」当成源码住在哪儿）。
MODULE_SOURCE = Path(_mentions_module.__file__)

INJECTABLE = "ok.py"
INJECTABLE_BODY = "INJECTABLE-PLAINTEXT-BODY"
MISSING = "nosuchthing"
BINARY = "binaryblob"
BINARY_BODY = "BINARYBODY"
DENIED = "secrets/keys"
DENIED_BODY = "top-secret-value"
OVER_BUDGET_FILE = "longblob"

BINARY_REASON = "二进制文件不注入内容"
MISSING_REASON = "工作区内没有这个文件"
OVER_BUDGET_ADVICE = "可用 read_file 读取"


def _workspace(root: Path) -> Path:
    """One fresh workspace per message: a verdict on one message must not
    depend on another message's writes."""
    (root / "secrets").mkdir(parents=True, exist_ok=True)
    (root / INJECTABLE).write_text(INJECTABLE_BODY + "\n", encoding="utf-8")
    (root / BINARY).write_bytes(b"\x00\x01" + BINARY_BODY.encode() + b"\x02")
    (root / OVER_BUDGET_FILE).write_text("line of text\n" * 400, encoding="utf-8")
    (root / DENIED).write_text(DENIED_BODY + "\n", encoding="utf-8")
    (root / ".minicc").mkdir(exist_ok=True)
    (root / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": [DENIED]}}), encoding="utf-8"
    )
    return root


def _block(root: Path, message: str, **kwargs) -> str:
    """The block a model would actually see for this message."""
    block, _records = build_mention_context(message, _workspace(root), **kwargs)
    return block


def test_a_binary_mention_is_named_even_with_nothing_injected(tmp_path: Path) -> None:
    """@binaryblob  alone: the verdict exists, the block used to be empty."""
    block = _block(tmp_path / "a", f"@{BINARY}")
    assert block != "", block
    assert f'<file path="{BINARY}" status="binary">{BINARY_REASON}</file>' in block, block
    assert BINARY_BODY not in block, block


def test_a_missing_mention_is_named_even_with_nothing_injected(tmp_path: Path) -> None:
    block = _block(tmp_path / "b", f"@{MISSING}")
    assert block != "", block
    assert (
        f'<file path="{MISSING}" status="missing">{MISSING_REASON}</file>' in block
    ), block


def test_a_rejected_mention_is_named_even_with_nothing_injected(tmp_path: Path) -> None:
    """改前零注入那侧唯一进块的判决——本批把它的家换掉，语义一字不改。"""
    block = _block(tmp_path / "c", f"@{DENIED}")
    assert f'<file path="{DENIED}" status="rejected">' in block, block
    assert "deny 规则不允许注入" in block, block
    assert DENIED_BODY not in block, block


def test_an_injection_still_annotates_the_other_verdicts(tmp_path: Path) -> None:
    """两个家并成一个之后，注入分支那条老路一条判决都不许掉。"""
    block = _block(tmp_path / "d", f"@{INJECTABLE} @{MISSING} @{BINARY}")
    assert f'<file path="{INJECTABLE}">\n' in block, block
    assert INJECTABLE_BODY in block, block
    assert f'<file path="{MISSING}" status="missing">' in block, block
    assert f'<file path="{BINARY}" status="binary">' in block, block


def test_the_block_is_empty_exactly_when_the_message_has_no_mention(
    tmp_path: Path,
) -> None:
    """派生不变式：块非空的唯一理由是这条消息里真的有 @-提及。"""
    for index, message in enumerate((
        f"@{MISSING}",
        f"@{BINARY}",
        f"@{DENIED}",
        f"@{INJECTABLE}",
        f"@{MISSING} @{BINARY}",
        f"@{BINARY} 还有 @{DENIED}",
        f"@{INJECTABLE} @{MISSING}",
        f"@{OVER_BUDGET_FILE}",
        "@" + "q" * 24,
        "没有问题，也没有引用",
        "这里的文件一个都不存在 @aa1.py @bb2.py @cc3.py",
    )):
        block = _block(tmp_path / "e" / str(index), message)
        has_mention = bool(extract_mention_tokens(message))
        assert (block != "") is has_mention, (message, has_mention, block)


def test_apply_mentions_still_leaves_a_mention_less_message_alone(
    tmp_path: Path,
) -> None:
    """边界的另一侧：没有提及的消息一个字节都不许多。"""
    workspace = _workspace(tmp_path / "f")
    message, records = apply_mentions("没有引用的问题", workspace)
    assert message == "没有引用的问题", message
    assert records == [], records
    with_mention, _ = apply_mentions(f"@{MISSING}", workspace)
    assert with_mention.startswith(f"@{MISSING}"), with_mention
    assert 'status="missing"' in with_mention, with_mention


def test_the_zero_injection_block_names_the_resolved_path(tmp_path: Path) -> None:
    """第五百三十一批的契约在新家里同样成立：path 是收敛后的那个值。"""
    block, records = build_mention_context(
        f"@secrets\\keys是什么", _workspace(tmp_path / "g")
    )
    record = records[0]
    assert record["path"] == DENIED, record
    assert f'<file path="{record["path"]}" status="rejected">' in block, block
    assert "secrets\\keys是什么" not in block, block


def test_the_annotation_sentences_each_have_one_home() -> None:
    """读者要看到的两句话各只被拼一次，手抄的那句拼法整个消失（M8-T549 的门）。"""
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    # 被拒那一句曾被抄成两个家（注入分支与零注入分支各一处）；收进一个助手之后，
    # 那个「按状态写死」的拼法必须一处都不剩——只数助手会放过「两处都改成助手」
    # 而助手自己没建起来的那种落法。
    hand_copied = 'status="rejected">{item["reason"]}'
    assert source.count(hand_copied) == 0, (
        f"被拒标注仍按状态手抄（{source.count(hand_copied)} 处），它应该由那一个家拼出"
    )
    for spelling in (
        'status="{item["status"]}">{item["reason"]}',
        "以下引用超出注入预算",
    ):
        count = source.count(spelling)
        assert count == 1, (
            f"标注句 {spelling!r} 在 mentions.py 里有 {count} 个家，应只有一个"
        )


def test_a_pure_loss_block_does_not_claim_it_injected_anything(tmp_path: Path) -> None:
    """块非空了，那句「以下内容已自动注入」就不能再骗人。"""
    lost = _block(tmp_path / "i", f"@{MISSING}")
    assert lost != "", lost
    assert "以下内容按 @-提及自动注入" not in lost, lost
    assert "需要完整内容时请用 read_file 工具重新读取" not in lost, lost
    read = _block(tmp_path / "j", f"@{INJECTABLE}")
    assert "以下内容按 @-提及自动注入" in read, read

def test_the_over_budget_note_offers_the_reader_the_same_way_out(
    tmp_path: Path,
) -> None:
    """超预算那条：无论块走哪个形状，读者都拿到「可用 read_file 读取」。"""
    block = _block(tmp_path / "h", f"@{INJECTABLE} @{OVER_BUDGET_FILE}", max_total_chars=20)
    assert "超出注入预算" in block, block
    assert OVER_BUDGET_ADVICE in block, block


def _emitted_statuses(source: str) -> set[str]:
    functions = {
        node.name: node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }
    assert "_record" in functions and "build_mention_context" in functions
    calls = {
        name: [node for node in ast.walk(function)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        for name, function in functions.items()
    }
    factories = {"_record"}
    while True:
        expanded = factories | {
            name for name, sites in calls.items()
            if any(site.func.id in factories for site in sites)
        }
        if expanded == factories:
            break
        factories = expanded

    for node in ast.walk(functions["build_mention_context"]):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "records"
                and node.func.attr == "append"):
            assert (len(node.args) == 1 and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id in factories), (
                "unresolved record producer", ast.dump(node))

    def visit(name: str, values: dict[str, str | None], stack: tuple[str, ...]) -> set[str]:
        assert name not in stack, ("recursive record factory", stack, name)
        if name == "_record":
            status = values.get("status")
            assert isinstance(status, str) and status, ("unresolved status", stack, values)
            return {status}
        statuses: set[str] = set()
        for call in calls[name]:
            target = call.func.id
            if target not in factories:
                continue
            parameters = functions[target].args
            positional = [arg.arg for arg in (*parameters.posonlyargs, *parameters.args)]
            bound = dict(zip(positional, call.args))
            assert all(keyword.arg is not None for keyword in call.keywords), (
                "unresolved keyword spread", name, call.lineno)
            bound.update({keyword.arg: keyword.value for keyword in call.keywords})
            resolved = {
                key: (value.value if isinstance(value, ast.Constant) and isinstance(value.value, str)
                      else values.get(value.id) if isinstance(value, ast.Name) else None)
                for key, value in bound.items()
            }
            statuses.update(visit(target, resolved, (*stack, name)))
        return statuses

    emitted = visit("build_mention_context", {}, ())
    assert emitted, "no reachable record statuses"
    return emitted


def _annotation_statuses(source: str) -> set[str]:
    assignments = [node for node in ast.walk(ast.parse(source))
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "annotations"
                           for target in node.targets)]
    assert len(assignments) == 1, ("annotation carrier", len(assignments))
    expression = assignments[0].value
    assert isinstance(expression, ast.ListComp) and len(expression.generators) == 1
    conditions = expression.generators[0].ifs
    assert len(conditions) == 1 and isinstance(conditions[0], ast.Compare)
    comparison = conditions[0]
    assert (isinstance(comparison.left, ast.Subscript)
            and isinstance(comparison.left.slice, ast.Constant)
            and comparison.left.slice.value == "status"
            and len(comparison.ops) == 1 and isinstance(comparison.ops[0], ast.In)
            and len(comparison.comparators) == 1), ast.dump(comparison)
    values = ast.literal_eval(comparison.comparators[0])
    assert isinstance(values, set) and values and all(isinstance(value, str) for value in values)
    return values


def test_every_annotation_status_has_a_reachable_record_producer() -> None:
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    emitted = _emitted_statuses(source)
    annotated = _annotation_statuses(source)
    assert annotated <= emitted, ("annotation states nobody emits", annotated - emitted)


def test_every_emitted_status_reaches_exactly_one_rendering_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    annotation_states: set[str] = set()
    body_states: set[str] = set()
    note_states: set[str] = set()
    observed: set[str] = set()
    original_annotation = _mentions_module._annotation_line
    annotation_records: list[dict] = []

    def annotation(item: dict) -> str:
        annotation_records.append(item)
        return original_annotation(item)

    monkeypatch.setattr(_mentions_module, "_annotation_line", annotation)
    scenarios = [
        (f"@{DENIED}", {}, False),
        ("@secrets\\keys是什么", {}, False),
        (f"@{MISSING}", {}, False),
        (f"@{BINARY}", {}, False),
        (f"@{INJECTABLE}", {}, False),
        (f"@{OVER_BUDGET_FILE}", {"max_chars_per_file": 20}, False),
        (f"@{INJECTABLE} @{OVER_BUDGET_FILE}", {"max_total_chars": 20}, False),
        (" ".join(f"@absent-{index}" for index in range(_mentions_module.MENTION_MAX_FILES + 1)), {}, False),
        (f"@{INJECTABLE} @{MISSING} @{BINARY} @{DENIED}", {}, False),
        (f"@{INJECTABLE}", {}, True),
    ]
    for index, (message, options, read_fails) in enumerate(scenarios):
        annotation_records.clear()
        workspace = _workspace(tmp_path / str(index))
        with monkeypatch.context() as context:
            if read_fails:
                original_open = Path.open

                def unreadable(path: Path, *args, **kwargs):
                    if path == workspace / INJECTABLE and args == ("rb",):
                        raise OSError("read failed after path resolution")
                    return original_open(path, *args, **kwargs)

                context.setattr(Path, "open", unreadable)
            block, records = build_mention_context(message, workspace, **options)
        assert records and block, (message, records, block)
        note_paths = {
            path for line in block.splitlines()
            if line.startswith("[truncated] 以下引用") and "读取：" in line
            for path in line.split("读取：", 1)[1].split("、")
        }
        for record in records:
            status, path = record["status"], record["path"]
            observed.add(status)
            is_annotation = any(item is record for item in annotation_records)
            is_body = f'<file path="{_mentions_module._attribute(path)}">\n' in block
            is_note = path in note_paths
            assert sum((is_annotation, is_body, is_note)) == 1, (
                message, record, (is_annotation, is_body, is_note), block)
            if is_annotation:
                expected = (
                    f'<file path="{_mentions_module._attribute(path)}"'
                    f' status="{status}">{record["reason"]}</file>'
                )
                assert expected in block, (record, block)
                annotation_states.add(status)
            if is_body:
                body_states.add(status)
            if is_note:
                note_states.add(status)
    assert observed == _emitted_statuses(source), (observed, _emitted_statuses(source))
    assert annotation_states == _annotation_statuses(source), (
        "annotation roster differs from rendered statuses", annotation_states, _annotation_statuses(source))
    assert not (annotation_states & body_states or annotation_states & note_states or body_states & note_states), (
        annotation_states, body_states, note_states)
    assert annotation_states | body_states | note_states == observed


def test_status_derivation_follows_wrapper_arguments_without_a_copied_vocabulary() -> None:
    source = '''
def _record(token, path, status, reason, truncated):
    return {"status": status}
def bridge(token, state):
    return _record(token, token, status=state, reason="", truncated=False)
def outer(token, verdict):
    return bridge(token, verdict)
def unused(token):
    return _record(token, token, "dead", "", False)
def build_mention_context(message, workspace):
    return [outer(message, "new_state"), bridge(message, state="other_state")]
'''
    assert _emitted_statuses(source) == {"new_state", "other_state"}
    renamed = source.replace('"new_state"', '"renamed"')
    assert _emitted_statuses(renamed) == {"renamed", "other_state"}
    unresolved = source.replace('outer(message, "new_state")', 'outer(message, message.upper())')
    with pytest.raises(AssertionError, match="unresolved status"):
        _emitted_statuses(unresolved)
    no_producer = source.replace('return [outer(message, "new_state"), bridge(message, state="other_state")]', 'return []')
    with pytest.raises(AssertionError, match="no reachable record statuses"):
        _emitted_statuses(no_producer)
    aliased = source.replace(
        'return [outer(message, "new_state"), bridge(message, state="other_state")]',
        'records = []\n    make = _record\n    records.append(make(message, message, "hidden", "", False))\n    return records',
    )
    with pytest.raises(AssertionError, match="unresolved record producer"):
        _emitted_statuses(aliased)
