# 集成清单：把 m8-t537 的所有集成工作合并进 main

本文是把现在 `m8-t537` 分支上的集成成果（`git grep`、`scripts/doc_pointers.py` 统一、协议/契约/phase/status 的归类与门、mentions/task/task_manager 的同一事实收口）以及 `main` 上的并行产物，汇集到一条线并通过验证的路线图。

## 我已经做了/准备好了什么

- `integration/mentions-xml-hardening3` / `integration/task-status-home` 两个分支分别对应两个未落地的小批次：
  - `3288e94` 已并入 m8-t537 的 `M8-T663`（mentions XML 折叠/转义收口）；
  - `dbc2656` M8-T665（task_manager 状态写入改用协议常量，防止再漂移出手写 `"running"`）。
- `m8-t537` 当前比 `origin/main` 多 230+ 条提交；`main` 本身也有近期并行产物（M8-T264/520+）。
- `scripts/doc_pointers.py` 已在统一实现里跑通；`--check` 出口 0 是当前门槛。

## 下一次合并必须同时回答的问题

1. **API 面一致性**：集成后 `minicc/mentions.py` 的判决词表、XML 块格式、以及 `build_mention_context` 的返回字段名仍保留 `MENTION_STATUS_*` 与既有门；否则 XML 硬化实际上会再 fork 一套字段家。
2. **契约面一致性**：`task_contract.RESULT_FIELD_*` 现在已被 `task_contract` ↔ `task_execution` ↔ `task_manager` ↔ `web` ↔ `task_worker` ↔ `benchmarks` ↔ `verifier` 多点生产和消费；如在 `main` 合并时，需全集群一致。
3. **行号尺一致性**：`scripts/doc_pointers.py` 迁移到 `_newline_index/_line_of` 后，`sections/check_evidence/check_links` 的计算代价从每 span 重算一次整个文档大头降到一次，`--check` 仍出口 0。
4. **task 生命周期**：`transition_status()` 不再接受裸 `"running"`/`"failed"`/`"interrupted"`；`PHASE_*` 与 `TASK_STATUS_*` 分域已立家允许重叠但不允许混用。

## 允许的分辨率顺序

- 优先保留 "能被已有 `--check` + 本地 test harness" 证明为同一事实的那部分。
- 保留能力更窄但可证明为同一事实的那一版；若两边都不能证明，把冲突型字面量放在一个新的 `decision` 模块里由竞争性测试逐项对账，而不是靠"我更熟悉"地瞎蒙。

## 按哪个顺序推进

1. 先确认 CI 42524276745（d537e0c, m8-t537）全绿；若不绿先红→绿+账本。
2. 以 `d537e0c` 为基底把 `integration/task-status-home`（当前待推）合入 `m8-t537`，CI 全绿再推送。
3. 在 `main` worktree 做合并：
   - `integration/*` 未并入 `main` 的内容全部评估；
   - 以 `origin/main` 为基底开 `integration/m8-t537-to-main`，先跑 `doc_pointers --check`，再跑全量回归。
4. 在 CI 全绿之前不要提交 `main`；记录冲突决议（每条不少于一行）。

## 封装约束

- 不保留合并冲突后产生的、仅存在于树里的 "备份" 文件；每一个 `_*.py` 都必须要么成为独立的 test 文件、要么被删除。
- 所有冲突决议都必须写进 `docs/ROADMAP_TO_PRODUCT.md` 的合并批次；纯重排/格式型冲突单独成批，不与行为型 hunk 合并。

## 验收（按顺序）

1. `python scripts/doc_pointers.py --check` → `exit 0`。
2. 本地 `pytest` 全量在 m8-t537 线→ 0 failed，monkeypatch 里所有门常量保持在同一个已立家的模块里。
3. 合并到 `main` 的 CI 全绿，`main` 本身 `git status` 在 CI 完成后清空（无未跟踪文件残留）。
