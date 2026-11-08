"""M8-T543 — 提及记录的 `path` 一名两义：收敛的写文件，没收敛的才写 token

改前在同一份临时工作区上实测（`permissions.json` 的 deny 规则点名
`secrets/k.txt`；`build_mention_context` 直接调用，5 条消息各 1 条记录）：

| 用户打的 token | `token` | `path` | status |
|---|---|---|---|
| `@src/a.py` | `src/a.py` | `src/a.py` | injected |
| `@src\\a.py` | `src\\a.py` | `src/a.py` | injected |
| `@src\\a.py是什么` | `src\\a.py` | `src/a.py` | injected |
| `@secrets\\k.txt是什么` | `secrets\\k.txt是什么` | `secrets\\k.txt是什么` | rejected |
| `@bin.dat是什么` | `bin.dat` | `bin.dat` | binary |

同一个文件在被注入时记 `src/a.py`，在被规则拒掉时记的是**用户原样**——反斜杠没换算、
CJK 粘连尾巴没削。事后按 `path` 关联「哪条规则拒了哪个文件」与「哪个文件真被注入了」
的消费者拿到两种拼法，而恰恰是被拒的那一条最需要对上号（它同时是块里给模型看的那句
标注，`mentions.py:292/294/305` 渲染的就是 `item["path"]`）。`token` 也在两个量之间
跳：回退收敛后的两条拒绝（`mentions.py:213/225`）写收敛前的 `original`（带尾巴），
其余分支写削过尾巴的 `token`——「用户到底打了什么」与「扫描器交出的是什么」同键混用。

本批把两个字段各定成一个量，并把边界写成一条可派生的不变式：

- `token` 永远等于 `_scan_mention_tokens` 交出的那一个（即 `extract_mention_tokens`
  的元素：只削尾部标点，不削 CJK 粘连尾巴）；
- `path` 在提及**收敛到一个真实工作区文件**时永远等于
  `resolved.relative_to(ws).as_posix()`，没收敛到时（绝对路径、`~`、盘符、越出工作区、
  回退到底也没有这个文件、超出条数上限根本没去解析）才等于 `token`——那一侧不存在
  「收敛后的路径」这个答案，造一个只会把没查过的事情写成查过。

于是 `path != token` 本身就是「这条提及解析到了一个真实文件」的记号，腿六按这个形状
普查；反过来把未收敛的 path 也做分隔符归一会废掉这个记号，本批不这么做。
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.mentions import build_mention_context, extract_mention_tokens

DENIED_FILE = "secrets/k.txt"
CREDENTIAL_FILE = ".minicc/web_token.json"
TAIL = "是什么"


def _workspace(root: Path) -> Path:
    """A fresh workspace per message: one record's outcome must not depend on
    another message's writes."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "secrets").mkdir(exist_ok=True)
    (root / "secrets" / "k.txt").write_text("top-secret-value\n", encoding="utf-8")
    (root / "bin.dat").write_bytes(b"\x00\x01BINARYBODY\x02")
    big = root / "big.txt"
    big.write_text("一行正文\n" * 4000, encoding="utf-8")
    (root / ".minicc").mkdir(exist_ok=True)
    (root / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": [DENIED_FILE]}}), encoding="utf-8"
    )
    (root / CREDENTIAL_FILE).write_text(json.dumps({"token": "C" * 48}), encoding="utf-8")
    return root


def _one(root: Path, message: str, **kwargs) -> tuple[str, dict]:
    block, records = build_mention_context(message, _workspace(root), **kwargs)
    assert len(records) == 1, (message, records)
    return block, records[0]


def test_a_denied_mention_names_the_file_the_rule_denied(tmp_path: Path) -> None:
    """收敛之后的拒绝记录写被拒的那个文件，不写用户手打的粘连尾巴。"""
    _block, record = _one(tmp_path / "a", f"@secrets\\k.txt{TAIL}")
    assert record["status"] == "rejected", record
    assert record["path"] == DENIED_FILE, record
    assert record["token"] == f"secrets\\k.txt{TAIL}", record


def test_a_credential_mention_names_the_file_the_gate_denied(tmp_path: Path) -> None:
    """M8-T65 的那条腿只问「有没有被拒」；这里问它记下的是哪个文件。"""
    _block, record = _one(tmp_path / "b", f"@.minicc\\web_token.json{TAIL}")
    assert record["status"] == "rejected", record
    assert record["path"] == CREDENTIAL_FILE, record
    assert record["token"] == f".minicc\\web_token.json{TAIL}", record


def test_the_refusal_the_model_reads_names_that_same_file(tmp_path: Path) -> None:
    """标注块是这条记录唯一的公开面，它必须与记录里的 path 是同一个值。"""
    block, record = _one(tmp_path / "c", f"@secrets/k.txt{TAIL}")
    assert f'<file path="{record["path"]}" status="rejected">' in block, block
    assert "top-secret-value" not in block, block


def test_three_spellings_of_one_file_share_one_path(tmp_path: Path) -> None:
    """注入记录的路径只有一个拼法，而 token 保留用户真正打下的三种写法。"""
    workspace = _workspace(tmp_path / "d")
    paths: set[str] = set()
    tokens: set[str] = set()
    for message in ("@src/a.py", f"@src\\a.py", f"@src\\a.py{TAIL}"):
        _block, records = build_mention_context(message, workspace)
        assert [r["status"] for r in records] == ["injected"], (message, records)
        paths.add(records[0]["path"])
        tokens.add(records[0]["token"])
    assert paths == {"src/a.py"}, paths
    assert tokens == {"src/a.py", "src\\a.py", f"src\\a.py{TAIL}"}, tokens


def test_a_refusal_and_an_injection_of_one_file_join_on_path(tmp_path: Path) -> None:
    """消费者真正要的：同一个 path 值既能出现「被拒」也能出现「被注入」。"""
    denied = _workspace(tmp_path / "e")
    (denied / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["src/a.py"]}}), encoding="utf-8"
    )
    _block, refused = build_mention_context(f"@src\\a.py{TAIL}", denied)
    assert [r["status"] for r in refused] == ["rejected"], refused
    assert refused[0]["path"] == "src/a.py", refused
    # 同一条路径在没有这条规则的工作区里就是被注入的那一条。
    _block2, injected = build_mention_context(
        f"@src\\a.py{TAIL}", _workspace(tmp_path / "e2")
    )
    assert [r["status"] for r in injected] == ["injected"], injected
    assert injected[0]["path"] == refused[0]["path"], (injected, refused)


def test_binary_and_over_budget_verdicts_name_the_resolved_file(tmp_path: Path) -> None:
    """二进制与「超出注入预算」两条腿也曾把收敛后的拼法写成 token。"""
    binary = _one(tmp_path / "f", f"@bin.dat{TAIL}")[1]
    assert (binary["status"], binary["path"], binary["token"]) == (
        "binary", "bin.dat", f"bin.dat{TAIL}",
    ), binary
    # max_total_chars=5：src/a.py 自己就把预算吃光（9 个字符截到 5），
    # 第二条才落到 remaining <= 0 的「超出注入预算」分支。
    _block, records = build_mention_context(
        f"@src/a.py @big.txt{TAIL}", _workspace(tmp_path / "g"), max_total_chars=5,
    )
    omitted = [r for r in records if r["status"] == "omitted"]
    assert [(r["path"], r["token"]) for r in omitted] == [
        ("big.txt", f"big.txt{TAIL}")
    ], records


def test_every_record_follows_the_one_quantity_rule(tmp_path: Path) -> None:
    """普查：`path != token` 只对「收敛到真实文件」成立，token 恒在扫描结果里。"""
    workspace = _workspace(tmp_path / "h")
    messages = (
        f"@secrets\\k.txt{TAIL}", f"@.minicc\\web_token.json{TAIL}",
        f"@bin.dat{TAIL}", f"@src\\a.py{TAIL}", f"@src/a.py{TAIL}",
        "@secrets/k.txt", "@src/a.py 和 @nosuch.py", "@/etc/passwd", "@~/x",
        "@C:/Windows/win.ini", "@../outside.txt", "@src\\nosuch.py",
    )
    for message in messages:
        _block, records = build_mention_context(message, workspace)
        scanned = extract_mention_tokens(message)
        assert records, message
        for record in records:
            assert record["token"] in scanned, (message, record, scanned)
            if record["path"] != record["token"]:
                assert (workspace / record["path"]).is_file(), (message, record)
                assert "\\" not in record["path"], record
                assert not Path(record["path"]).is_absolute(), record
                assert not record["path"].startswith("../"), record


def test_an_unresolved_mention_has_no_other_answer_to_give(tmp_path: Path) -> None:
    """边界：没收敛到文件时 path 就是原样——那时不存在「收敛后的路径」。

    未收敛那侧**不做分隔符归一**：`(ws / path).is_file()` 这个记号靠的正是
    「path 不等于 token 当且仅当它落到了真实文件」。把 `src\\nosuch.py` 也写成
    `src/nosuch.py` 会让读的人以为有人查过。
    """
    for index, (message, expected) in enumerate((
        ("@C:/Windows/win.ini", "C:/Windows/win.ini"),
        ("@../outside.txt", "../outside.txt"),
        (f"@nosuch.py{TAIL}", f"nosuch.py{TAIL}"),
        ("@src\\nosuch.py", "src\\nosuch.py"),
    )):
        _block, record = _one(tmp_path / f"i{index}", message)
        assert record["path"] == expected, record
        assert record["token"] == expected, record


def test_the_record_shape_still_has_exactly_the_five_fields(tmp_path: Path) -> None:
    """M8-T407 的五个字段一个不多一个不少——本批改的是值从哪来，不是形状。"""
    _block, record = _one(tmp_path / "j", f"@{DENIED_FILE}{TAIL}")
    assert set(record) == {"token", "path", "status", "reason", "truncated"}, record
    # 五个字段之外还要钉一个值：新助手的 truncated。被拒的提及没有任何内容
    # 被截断注入，写成 True 就是一条假话。
    assert record["truncated"] is False, record
