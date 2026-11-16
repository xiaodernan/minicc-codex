from pathlib import Path

changelog_addition = """

- **说明书第十七章「并行子智能体 / Parallel Subagents」+ Atlas 79（M8-T1095 / 批次 1080）**：说明书第十七章把 minicc/agent/orchestration.py 的评分表原件摊开——`AUTO_FANOUT_THRESHOLD=4` / `AUTO_FANOUT_MAX_CHILDREN=3` / DIMENSION_PATTERNS（inspection·implementation·verification·research·presentation）/ `_CONNECTOR_RE`（word-boundary，见 M8-T290 堵 "understanding" → "and" 的隐患）/ `_OPT_OUT_RE` / `_FILE_RE` / `assess_complexity()` 不发模型调用、纯函数可复现。zh/en body 全部落到文件级 [(`{._decode_*}` markers; M8-T296 budget partially passes any child `BudgetExceeded` honestly.
"""
p = Path("docs/CHANGELOG.md")
t = p.read_text(encoding="utf-8")
if "M8-T1095" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += changelog_addition.lstrip("\n")
    p.write_text(t, encoding="utf-8", newline="\n")
print("changelog: appended M8-T1095")

roadmap_addition = """

## 批次 1080 · M8-T1095: 说明书第十七章「并行子智能体 / Parallel Subagents」—— Atlas 79

### 目的

Manual 第 14 章是 fanout 的人格面板，第 17 章是硬件 — 直接拆开 minicc/agent（orchestration 与 graph），把常量变成散文。

### 做了什么

- **`web/src/panels/manual.js`**：新增 `zhFanout`/`enFanout` + BODIES 注册（Chapter 17 · 十七 · 并行子智能体）；Atlas 行 78→79 / 16→17 manual satellites。
- **Atlas 78 → 79 coordinates**：manual satellites 16→17；`atlas_smoke` 79；welcome chips 79（i18n.js CRLF 309/0）；index.html 711/0。
- **README / onboarding / Manual Atlas 行**：把七个实测常量全部落到 README bullet / 十七说明书卫星。
- **验证**：`manual_smoke` 17 chapters 全双语 / `atlas_smoke` 79-coordinate / `parity` / `admin_smoke` / dazzle / CRLF pins 711/0 + 309/0。
"""
p = Path("docs/ROADMAP_TO_PRODUCT.md")
t = p.read_text(encoding="utf-8")
if "批次 1080" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += roadmap_addition.lstrip("\n")
    p.write_text(t, encoding="utf-8", newline="\n")
print("roadmap: appended 批次 1080")
