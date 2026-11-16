from pathlib import Path

changelog_addition = """

- **年鉴卷四十四「无眠 / The Sleepless」+ Atlas 80（M8-T1096 / 批次 1081）**：卷四十四把这次会话真实登记的日子写进年鉴——Digest 一路走到底：1,767 commits（as of 2026-11-16T16:00 UTC+8 / fact pack `c7bdd74`）· almanac 44 chapters（now 45 after this chapter) · 79 Atlas coordinates（→80) · 1096 tracked_files / 716 test_files · roadmap_batches=407 · 没有一次停手；M8-T1083 (Ch.38）真故事衔接至 Ch.44；197 direct API calls through the new lane measured · 0 non-2xx/non-Connky · 5-minute TTL folklore formally retired (M8-T1078 ladder-A/B/C/D)。CHAPTERS/CHAPTER_RENDERERS 注册 `sleepless`；instrument grid 直播 commits/tasks/recent/Atlas 80/45-45 卷/17-17 说明书/受跟踪文件 1096/测试 716；Atlas 升至 **80 坐标**（18+45+17）；welcome chips 80；tests/almanac_smoke 45 章润色；`atlas_smoke` 80-coordinate · `manual_smoke` 17 · parity en zero CJK / admin / dazzle / CRLF pins 711/0 + 309/0。
"""
p = Path("docs/CHANGELOG.md")
t = p.read_text(encoding="utf-8")
if "M8-T1096" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += changelog_addition.lstrip("\n")
    p.write_text(t, encoding="utf-8", newline="\n")
print("changelog: appended M8-T1096")

roadmap_addition = """

## 批次 1081 · M8-T1096: 卷四十四「无眠 / The Sleepless」—— Digest 一路到底，一天数本书；Atlas 80

### 目的

这一卷不是口号，是“整夜从头跑到底，从来不停手”。凡是被本会话亲眼见证一次 landing 的数字，都在这一页里。

### 做了什么

- **`web/src/panels/almanac.js`**：新增 `sleeplessMarkup()`（卷四十四 · 无眠）+ CHAPTERS + `CHAPTER_RENDERERS['sleepless']`；双语 body 各自成立；id=sleepless；quote-end「从不等天亮的仓库——它知道日出是什么」。
- **Atlas 79 → 80 coordinates**：almanac satellites 44→45；`atlas_smoke` 80；welcome chips 80（i18n.js CRLF 309/0）；placeholders 80（index.html 711/0）。
- **onboarding / Manual Atlas 行 / README**：seventy-sixteen chapters / forty-five halls；README 以 The Sleepless 领衔。
- **验证**：`almanac_smoke` 45 chapters 双语全绿 / `atlas_smoke` 80-coordinate / `parity` / `manual_smoke` 17 / `admin_smoke` / dazzle / CRLF pins 711/0 + 309/0。
"""
p = Path("docs/ROADMAP_TO_PRODUCT.md")
t = p.read_text(encoding="utf-8")
if "批次 1081" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += roadmap_addition.lstrip("\n")
    p.write_text(t, encoding="utf-8", newline="\n")
print("roadmap: appended 批次 1081")
