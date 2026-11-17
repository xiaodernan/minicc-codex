# -*- coding: utf-8 -*-
"""Ledger entries for M8-T1132."""
from pathlib import Path

changelog_addition = """- **CLI 双语化 第 3 段——ratchet 清零：每一个键都有生产者（M8-T1132 / 批次 1107）**：批次 1105/1106 后 ratchet 还剩 32 个无人读的键。本批逐个判定：**13 个键有真实活调用点，全部接线**——session.py 的 `会话不存在/session 格式错误/fork 点无效/fork_min_keep/fork_max_keep/rewind_min/user_index_min/rewind_no_user`、git.py 的 `git 命令失败/branch 参数非法`、memory.py 的 `（暂无记忆条目）`、main.py 的 `未知命令`（`test_a_command_file...` 的钉仍绿）；**19 个键在 main 里根本没有对应消息**（`unknown_tool`/`tool_error`/`invalid_args`/`absolute_path`/`path_outside`/`denied_*` 等都是 backup 线遗留、main 早已改用别的错误面）——**如实删除**（两表各 38 行），不留着假装翻译。`rewind_no_session` 与 `session_not_found` 是同一条消息两个键名（同一调用点），同名收敛。结果：**消息表 129 键、无人读键 = 0**——`UNREAD_KEYS_BASELINE = frozenset()`，`test_cli_i18n.py` 的 ratchet 三腿在地板上跑。**诚实边界**：`task_manager.py` 引擎内联文案（约 120 处面向工程师排障与模型的中文）**仍未接**——登记为 M8-T1133（engine 面接线）；本批不把 CLI 说成全量双语。CI 这一刻仍在跑；不把它写成绿。
"""

p = Path("docs/CHANGELOG.md")
t = p.read_text(encoding="utf-8")
if "M8-T1132" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += changelog_addition
    p.write_text(t, encoding="utf-8", newline="\n")

roadmap_addition = """

## 批次 1107 · M8-T1132: CLI 双语化 第 3 段 — ratchet 清零（每一个键都有生产者）

### 做了什么

- **接线 13 个**：session.py（`会话不存在` / `session 格式错误` / `fork 点无效` / `fork 点至少为 1` / `fork 点超出` / `keep_messages 至少为 1` / `user_index 至少为 1` / `会话中没有第 N 条 user 消息`）、tools/git.py（`git 命令失败` / `branch 参数非法`）、tools/memory.py（`暂无记忆条目`，原全角括号形状保留）、main.py（`未知命令`，与 `test_a_command_file...` 的逐字钉对齐）。
- **删除 19 个**：main 中不存在对应消息的 backup 遗留键（`unknown_tool` / `tool_error` / `tool_exception` / `invalid_args` / `system_io_error` / `tool_denied` / `absolute_path` / `path_outside` / `branch_invalid` 已接线、`denied_write` / `denied_exec` / `mcp_*` 五个 / `memory_not_found` / `memory_written` / `session_error` / `workspace_not_dir`）。
- **收敛 1 个**：`rewind_no_session` 与 `session_not_found` 同文、同调用点，只留后者。
- **表 129 键，ratchet 归零**：`UNREAD_KEYS_BASELINE = frozenset()`；`test_cli_i18n.py` 三腿（无人读键不许超过基线 / 基线不许含已接线键 / 基线不许含已消失键）在 0 上运行。
- **en/zh 实测**：`MINICC_LOCALE=en_us` 全链路英文（REPL 语料、`--help`、权限理由、doctor、fork/rewind）；默认 zh_cn 输出逐字节不变。

### 绑定的诚实边界

- `task_manager.py` 引擎内联文案（约 120 处，面向工程师排障与模型语境）**没有接**——登记 **M8-T1133**：engine 面双语化（`[BUDGET]` 等标记部分 ASCII-only 可直接保留前缀，中文句接入表）；不做成“engine 双语已完成”。
- `/view` 历史文件中存的旧中文文案不追溯改写。
- 零产品行为变化：表与 import 之外全是 `tr()` 调用替换。
- CI 这一刻仍在跑；不把它写成绿。
"""

p = Path("docs/ROADMAP_TO_PRODUCT.md")
t = p.read_text(encoding="utf-8")
if "批次 1107" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += roadmap_addition.lstrip("\n")
    p.write_text(t, encoding="utf-8", newline="\n")
print("ledgers appended")
