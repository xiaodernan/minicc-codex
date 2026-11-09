# 集成清单：把 m8-t537 的所有集成工作合并进 main（归档 + 验收回填，2026-11-09）

本文原是合并前的路线图。合并已完成并通过 CI（本文件保留为**决策记录**而不是行动项）。下面每小节按时间线回填实况；原有清单原文已不可见，如需追踪请见 `git log docs/INTEGRATION_STRATEGY.md`。

## 实际落地路径（与原计划的一一对应）

1. **核对并本地合入 `integration/task-status-home`**（`task.status = "running"` 的协议常量改写）：先文末全绿 → `git cherry-pick dbc2656` → `m8-t537@c3ad1ec` + 批 647；CI 已绿。
2. **主线 `integration/m8-t537-to-main` 第一阶段（批 668 合流批）**：
   - 顺序：在 `main` worktree 拉分支 → `git merge m8-t537`；
   - 冲突逐文件决议（`permissions.py` / `audit.py` 取集成线版；`changes.py` 以主通道为基底接回 `m8-t537` 的 M8-T551 git-probe reason 4 元组；`task_manager.py` 以集成线版为基底补回 `LEASE_REVIVAL_GRACE_SECONDS` + `stale_since` 宽恕窗；`test_retrieval_enhanced.py`、`test_one_refresh_asks_the_rules_once.py` 等）；
   - `ROADMAP_TO_PRODUCT.md`：L519–521 一节被**订正**（集成通道在此写下了不存在的 content-hash / per-file 探测实现，撤下重写为「并轨补记 — M8-T537/538/539」）；两侧批次号同号不同事——主通道改记为 `第六百四十八批–第六百六十七批`（内容一字未动，宣文保留原名），从六百六十八批起编号不回收；
   - 并轨后 `doc_pointers --check` rc=0；两轮双腿红踩红 → 批 671/672 订正（loader 注册形态 + `_SIBLING_CITATIONS` 去 dup；census 门扩展为解常量）。
3. **主线快进 + 验收**：
   - `main` 快进到合并结果（`36b20cf` 起）；CI `42536933250` ubuntu-windows 双腿全绿；
   - `integration/m8-t537-to-main` 与 `origin/main` 在同一 SHA；`dev/minicc-reliability-4ba3` 也快进到 `c281903`，被合入为批 670。
4. **后续批次**（批 673–680）：6 个 one-home 收口 + 合流红修（批 677）全部落在主线，CI 全绿再推送。

## 合并决议的学到的（写在这里以免重复）

- **同号不同事**——两条通道在同一个 `docs/ROADMAP_TO_PRODUCT.md` 里续写 `第五百XX批`，编号空间完全重了。教训：**编号只能沿一条线续写**；续号前 `scripts/doc_pointers.py` 的「声明唯一」门能抓住撞号，但不能替代合并时的逐节审阅；修法是合流纪录里逐字保留两节并订正编号，不是改写任何一边历史。
- **合流的 `.ROADMAP` 伪记录**——合并前（`243b649` 一个纯装饰提交，全是「五字段 content-hash 缓存」「stat 529→250」之类的编造读数）必须作为**订正**而不是合入：字面没发生过的事实在合流纪录里改写为真蓝图，追踪的是 bug 而非风格。
- **行号引用**——合并导致的批次行号整体漂移：`test_the_sibling_citations_keep_their_reader_and_their_line` 对同名兄弟引用反复红两次，都是因为两批互不知道对方在写 `path:line`。
- **git EOL 守卫**——合并与后续批次反复把 CRLF 文件改写成 LF（`git diff --stat` 7000+ 行变动），必须**先查 EOL、再补 CRLF、再 `git checkout` 归零 再重做**；不然纪录被换行盖过内容。

## 目前仍然 open 的项（都不在本仓库内）

- `backup/local-line-batches70-75`：`669eae5`（`sampling_enabled` 配置骨架，无 handler 任何分支都不消费）**不合**；保留只作历史参照。
- `integration/m8-t537-to-main`、`integration/mentions-xml-hardening3`、`integration/task-status-home`、`integration/ci-web-smoke`、`integration/mentions-security`、`integration/mentions-xml-hardening`：均已并入，保留为未来追踪用途。
- `D:\面试项目\wt*`、`D:\面试项目\plane*` 等旧 worktree 属于其它会话；不动。
- `D:\面试项目\minicc-codex-scratch\`（原 `_*` / `scratch/` 的搬迁落点，**字节原样未删**）：遗留测量脚本，保留自用。
- 剩余 CI 牙缝：nightly 真实 key 评估按需手动跑；夜间/周末 cron 决定起停，不在本批处理。
