# -*- coding: utf-8 -*-
from pathlib import Path

changelog_addition = """- **一个事实一个家，第二地**：「网关预算」瓷贴的专用路线撤了，数据改吃解锁包里早就有的 `ratelimit`（M8-T1014 埋在 `build_summary` 里的土生土长成员）——M8-T1180 的 `/api/admin/ratelimit` 是一条**额外的同一件事的第二张脸**（CI 六只兔子而已逮了我的名册；这两条红门都证明更少的门路比更多的门路好）。改动：`webserver.py` 专用端点删除；`tests/test_http_surface.py` 双腿同时撤回；`admin.js` 的 `renderRatelimit` 改从 `loadSummary()` 的 `/api/admin/summary` 载荷取数，刷新按钮故去（瓷贴渲染挂在解锁/重载的那一次总读取上，同其余 tile 家庭）；`i18n.js` 双语键 `admin.ratelimitRefresh` 撤回（814→815→815 门仍绿，259 t() 引用全解）；`index.html` 瓷贴去掉专用刷新按钮。**路由总数 39→40→39**；815 键 zh/en 齐整。
"""

p = Path("docs/CHANGELOG.md")
t = p.read_text(encoding="utf-8")
if "M8-T1185" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += changelog_addition
    p.write_text(t, encoding="utf-8", newline="\n")

roadmap_addition = """
## 批次 1128 · M8-T1185: 网关预算归位——回到解锁包里，不再多此一路

### 目的

M8-T1180 给管理面板加了「网关预算」瓷贴并同时铺一条专用 HTTP 路线 `/api/admin/ratelimit`。审查发现 `/api/admin/summary` 早在 M8-T1014（admin v1）把 `ratelimit` 嵌在 `build_summary` 里返回给解锁面板——同一件事铺了两条线，正属本仓门禁文化明令的一类病（今日 CI 里 impact floor 与 re-aimed citation 各红一把，同属一类病根「多一份不只多一份负担」）。

### 做了什么

- **端点删除**（`minicc/webserver.py`）；对应 HTTP 门禁撤回（`test_http_surface.py`，98→97）。
- **瓷贴改吃解锁载荷**：`renderRatelimit(data?.ratelimit ?? null)` 挂进 `loadSummary()`——同一次 `/api/admin/summary` 旅程里渲染，不再有冗余连线；刷新按钮撤掉（瓷器在解锁/重载时即刻反映最新闸尺计数），i18n 键 `admin.ratelimitRefresh` 撤回（zh/en）。
- **门禁仍绿**：frontend dict 815 键双边 + 259 t() 引用；`http_surface` 97 条；CRLF 双文件 0 LF-only；en_cjk / RAG / admin 冒烟全绿；`summary` 真查取到 `{limit:20, decisions{allowed_local:24, allowed_redis:0, denied:0, degraded_open:0}, remaining_local_windows:8}`。

### 不声称

- 不改闸门本身语义：共享 60s/20 尺寸不动、Fail-open 不动、Redis/LRU 后备不动、`ratelimit.stats()` 计数器不动。
- 不撤路由注册机制：其余 8 个网关花钱路由仍然进共享闸门，语义不动。
- 不改 `build_summary` 的 15s memo：预算计数同其余 tile 一同吃 memo，与解锁后的所有面板读数一致。
"""

p = Path("docs/ROADMAP_TO_PRODUCT.md")
t = p.read_text(encoding="utf-8")
if "批次 1128" not in t:
    if not t.endswith("\n"):
        t += "\n"
    t += roadmap_addition.lstrip("\n")
    p.write_text(t, encoding="utf-8", newline="\n")
print("ledgers appended")
