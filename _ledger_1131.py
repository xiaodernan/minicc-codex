# -*- coding: utf-8 -*-
"""Ledger entries for M8-T1131."""
from pathlib import Path

changelog_addition = """- **CLI 双语化 第 2/2 段——`--help` 面、授权决策理由、doctor/命令文件面全部接线（M8-T1131 / 批次 1106）**：批次 1105 接的是 main.py 交互面；本批把剩下三类用户可见的中文全部接入消息表（zh_cn/en_us 各 148 键、逐键对仗）：**① argparse `help=` 的 39 条 + 解析器 description**（`--help` 在 `MINICC_LOCALE=en_us` 下全英文，实测 `--help` 逐选项英文输出）；**② audit.py 的授权裁决理由全部 25 条**（`AuthorizationDecision.reason`——用户在拒绝提示里看到的每个字，例如「计划模式只允许只读工具，写入已拒绝」→ `Plan mode allows read-only tools; write denied`）；**③ doctor.py 的四条修复建议行、commands.py 的命令文件损坏提示/技能目录抬头/技能目录行**。ratchet 基线从 34 缩到 **32**（本批接线 74+ 个新键，无人读的仅剩 engine 错误面，全列在 `UNREAD_KEYS_BASELINE`，只缩小不放大）。`test_cli_i18n.py` 现在钉：148/148 对仗、`tr` 不 raise、baseline 三腿（无新无人读键 / baseline 不藏已接线键 / baseline 不含已消失键）。**诚实边界**：`task_manager.py` 引擎面、`tools/registry.py` / `tools/fs.py` 等的错误文案（32 个 ratchet 键）仍是中文——那是面向工程师排障与模型的内联消息，接进同一双语体系是下一批（M8-T1132）的工作，**不是这批已经做完的**。CI 这一刻仍在跑；不把它写成绿。
"""

p = Path("docs/CHANGELOG.md")
t = p.read_text(encoding="utf-8")
if "M8-T1131" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += changelog_addition
    p.write_text(t, encoding="utf-8", newline="\n")

roadmap_addition = """

## 批次 1106 · M8-T1131: CLI 双语化 第 2/2 段 — `--help` 面、授权理由、doctor/commands 全部入表

### 做了什么

- **cli_io.py 消息表 75 → 148 键**（两表逐键对仗，仍是同一 `tr`/降级契约）。
- **main.py argparse**：parser `description` + 39 条 `help=` 全部改 `tr("arg_*")`；`MINICC_LOCALE=en_us minicc --help` 实测逐选项英文（含 description 行）。
- **audit.py**：`AuthorizationDecision.reason` 的 25 条中文裁决理由全部接入（`audit_*` 键）——这是用户权限提示下看到的每个字。
- **doctor.py**：升级 python/unit/重装 wheel/检查目录写权限/检查 .minicc/ 所有者四条建议接入。
- **commands.py**：`reason_text`（编码读不出来/操作系统不给读）、命令文件损坏的整句提示、技能列表抬头、技能文件目录行接入。

### 守门

- zh_cn 输出逐字节不变（所有新键的 zh 文案逐字照抄原字符串，相关既有断言全绿：main/slash_commands/permission_modes/audit_authorization/doctor/commands 邻域 122+110 条）。
- `test_cli_i18n.py`：ratchet 32 键（engine 面，列账清晰），表 148/148 对仗；baseline 三腿全绿。
- `--help` 实测：en_us 输出英文，zh_cn 默认输出中文。

### 诚实边界（不声称）

- `task_manager.py` 等引擎内联文案（约 120 处双引号中文：预算/取消/校验等面向工程师排障与模型的消息）**未接**——登记为 **M8-T1132**：engine 面接线 + registry/fs 工具面错误文案 + 剩下的 32 个 ratchet 键归零。
- 本批没有动 CLI 的通道输出之外任何行为；`git diff --stat`：+236/-78 行，零产品行为变化（表与 import 之外全是 tr() 调用替换）。
- CI 这一刻仍在跑；不把它写成绿。
"""

p = Path("docs/ROADMAP_TO_PRODUCT.md")
t = p.read_text(encoding="utf-8")
if "批次 1106" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += roadmap_addition.lstrip("\n")
    p.write_text(t, encoding="utf-8", newline="\n")
print("ledgers appended")
