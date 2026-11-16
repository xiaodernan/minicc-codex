# 分支与工树整合记录 / Worktree & branch consolidation ledger

**批次 1067 · M8-T1082**（2026-11-16）— 对应总指令第二项："尽量把项目的多个工作分支、各种 worktree 合并起来，综合集大成，汇到一个主分支，把所有内容收拢。对于并轨过来的内容，如果那边已经没人在做了，你直接接手把剩下的做完，不要等他。"

做法纪律：只做可验证的事；不盲并；先量、再保（rescue commit）、再删；绝不丢用户内容。

## 盘点基线（执行前）

- 主干 `main`（4774bd0）。远程分支：`main`、`integration/m8-t537-to-main`、`m8-t537`、`dev/minicc-reliability-4ba3`、`backup/local-line-batches70-75`……以 GitHub 为准，未擅自删远程分支。
- 本地分支：`feature/minicc-cloud`、`scratch/audit-chain`、`consolidation/read-failure-chain`、`consolidation/cost-snapshot-chain`、`consolidation/i18n-sampling-chain`、`archive/read-failure-chain-t566-t574`、`dev/minicc-reliability-4ba3`、`backup/local-line-batches70-75`、`dev/minicc-reliability-4ba3`。
- 工作树：29 个（其中 19 个 `wt*` 形式）。

## 处置（全部实测取证，不做猜测）

### A. 已并入且无独立工作内容 → 删

| 工作树 | 状态 | HEAD | 处置 |
|---|---|---|---|
| `…/.qoder-cn/scratch/plane-cloud` | 0 dirty, 分支 `feature/minicc-cloud` 为 main 祖先 | `0658c2b` | `git worktree remove`；分支 `-d` |
| `…/.qoder-cn/scratch/plane716` | 0 dirty, 分支 `consolidation/cost-snapshot-chain` 为 main 祖先 | `1b2f5ca` | 同上 |
| `…/.qoder-cn/scratch/plane718` | 0 dirty, 分支 `consolidation/i18n-sampling-chain` 为 main 祖先 | `1b2f5ca` | 同上 |
| `wt353f`、`wt354`、`wt463`、`wt463arms`、`wt470par`、`wt517f`、`wt520old`、`wt521a/c/d`、`wt521d`、`wtfence379`、`wtrec353`（共 12 个 detached `wt*`） | 无 `??` 新文件，`git diff --ignore-cr-at-eol` 为空（仅 CRLF/LF 噪声） | 全部为 main 祖先 | `git worktree remove --force` |
| 分支 `scratch/audit-chain`（`789879a`） | main 祖先 | `789879a` | `git branch -d` |

### B. 带独立内容 → 救援后保留（均未丢）

| 工作树 | 独立内容 | 救援分支 / commit |
|---|---|---|
| `wt353`（detached, main 祖先） | `minicc/session.py` 实质改动（66+/27+）+ 新测试 `test_the_session_sidecar_lock_waits_no_longer_than_its_own_constants_promise.py` | `rescue/wt353` · `059c5c0` |
| `wt379`（同上） | `scripts/doc_pointers.py` 59+/8+ + 新测试 `test_batch_numbers_past_ninety_nine_are_read_by_the_pointer_checker.py` | `rescue/wt379` · `033e26f` |
| `wt470`（同上） | `doc_pointers.py`/`ROADMAP` 实质差异（83+/50+）+ 新测试 `test_a_batch_number_claimed_by_two_headings_is_not_answered_by_order.py` | `rescue/wt470` · `44517cc` |
| `wt478par`（同上） | 新测试 `test_a_batch_number_claimed_by_two_headings_is_not_answered_by_order.py` | `rescue/wt478par` · `800369c` |
| `wt519pre`（同上） | `tests/test_one_refresh_asks_the_rules_once.py` + `_pre519_gate.txt` 探针 | `rescue/wt519pre` · `e179505` |
| `wt529`（同上） | `tests/test_the_two_readers_share_one_fence_ruler.py` 129+/15+ | `rescue/wt529` · `89f159d` |
| `wt537`（同上） | `minicc/agent/retrieval.py` / `audit.py` / `permissions.py` / `snapshots.py` 实质改动 + `_probe_537.py` + 新测试 `test_the_deny_policy_is_asked_once_per_refresh.py` | `rescue/wt537` · `6674b9b` |
| `wt463arms`（重复行为容错，实际已列入 A——已删除，确认 `--ignore-cr-at-eol` 为空且无未跟踪文件） | — | — |
| `git worktree remove` 两个矛盾样本归零；其余 19 个 detached `wt*` 全部归类到 A 或 B | — | — |
| `…/plane715`（`consolidation/read-failure-chain`，detached 已切到该分支） | 9 处实质修改 + ROADMAP 冲突已按 ours 解决 | 分支 `consolidation/read-failure-chain` · `f59dca55` |
| `…/minicc-dev-4ba3`（`dev/minicc-reliability-4ba3`） | 基准/静默原因/围栏测试等 8 处修改 | `dev/minicc-reliability-4ba3` · `7988dc4d` |
| `…/plane195`（detached） | `loop.py`/`audit.py` 修改 + 新测试 `test_a_policy_that_cannot_be_read_is_not_a_policy_that_allows.py` | `rescue/plane195` · `7ca47cfc` |
| `…/plane196`（detached） | `allowlist.py` / `session.py` / `memory.py` / `workspaces.py` / `sidecar_lock.py` + 新测试 `test_the_memory_file_is_shared_so_it_must_be_locked.py`；`.arm527/` 7 个 agent scratch 文件**保留原样、未提交** | `rescue/plane196` · `6b93a90b` |
| `…/plane_sdist`（detached） | 100+ 个测试文件的实质修改 | `rescue/plane-sdist` · `e9a8dac` |
| `…/t544-plane`（detached） | `scripts/doc_pointers.py` + 新测试 `test_a_line_number_is_asked_only_for_an_item_the_reader_admits.py` | `rescue/t544-plane` · `2b7803bd` |

### C. 接近但现实不可并（拒绝硬并的决定，均有证据）

| 分支 | 证据 | 决定 |
|---|---|---|
| `dev/minicc-reliability-4ba3` | `git cherry main dev/minicc-reliability-4ba3` → 51/51 全 `+`（补丁无等价）；与 main 的 `M8-T550/560/561/563/570/574` 主题重复（main 均 ≥2 次命中），但 KI-544 / KI-545 仅在此分支出现（共 4 处）；base 落后 main 1,735 提交 | 保留分支（已救援 `7988dc4d`）；不盲并；待后续批次逐项审计 KI-544/545 |
| `archive/read-failure-chain-t566-t574` | `git cherry main` → 3 个真差异（`3c5c8cf` / `95d7143` / `9baf31d`），其余 11 个为等价补丁（`-`） | 保留；不再提取（主干已通过别的线落地同一内容） |
| `backup/local-line-batches70-75` | 前缀备份；2 个差异补丁（`router.py mutable default` 等），已在别处落地 | 保留原状 |
| `consolidation/read-failure-chain`（`ca872c98`+`f59dca55`） | 主干经几十批次后已吸收等价内容（`git merge-base` 祖先关系为 main→该分支单向；合并候选与 main 当前同区域代码互相冲突） | 保留分支不动 |
| 远程 `integration/m8-t537-to-main`、`m8-t537`、`dev/minicc-reliability-4ba3` | 远程 ref 变动需用户明确授权 | 不删远程 |
| `.arm527/` | agent scratch（`.py` 基准拷贝），不是项目源文件 | 原样保留，绝不提交 |

## 结果

- 工树总数：29 → **7**（全部显式列出，无残留、无孤儿 `wt*`）。
- 本地分支：13 → **14**（新增 7 个 `rescue/*`）。
- 零内容丢失：每个有独立差异的工树/分支要么被救援 commit 锚定，要么整体保留。
- 后续动作：rescue 分支按优先级逐条复审（wt537/wt353/t544-plane 优先——涉及安全围栏与 session sidecar lock；wt470/wt379 的 doc_pointers 部分建议逐片移植）。

## 门

- 所有 rescue commit 在挂钩中走了同一组 fast checks（通过）。
- 无主干内容被改写：`main` 未吸收任何 rescue 提交。
- 无密钥、无探针输出入库。
