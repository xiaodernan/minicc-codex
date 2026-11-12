# minicc 集大成审计与归并报告

> 基线：`main` @ M8-T820（真实 API 跑通 + `name:null` 修复）。审计日期：2026-11-12。
> 配套证据：7 个 `consolidated/*` annotated tag；逐提交判定见文末方法。
> 本文回答一个问题：**项目历史上分叉出的分支与 worktree，内容是否都已汇集到 main？还欠什么？**

## 一、结论（一句话）

**没有需要移植的真缺失功能。** 7 个历史分支的内容已全部汇入 main（4 个逐提交证明已进且多更强、1 个被架构明确否决、2 个主体被 main 自有批次取代）；23 个测量平面 worktree 中 22 个 HEAD 已在 main 历史，唯一例外 `t544-plane` 的 43 个提交对 `minicc/`、`web/src/` 生产文件的 diff 为**空**（只含私有 docs/tests 记录）。因此"合并到主分支"的正确动作不是制造一批会冲突/回退的空 merge，而是**用 tag 固化归并结论 + 保留分支与平面作证据**，main 已是事实上的集大成者。

## 二、7 个历史分支的处置

判定方法：`git cherry -v main <branch>` 取 patch-id 差集 → 对每个 `+`（patch-id 独有）提交看真实 diff（不信中文标题）→ 在 main 工作树 grep/import 它引入的关键符号 → 判 `ALREADY_IN_MAIN` / `OBSOLETE` / `TRULY_MISSING`。

| 分支 | patch-id 独有 | 处置 | 归档 tag |
| --- | --- | --- | --- |
| `feature/minicc-cloud` | 0 | **已完全合入**（骨架 M8-T717、配置中心 M8-T719 两次合流） | `consolidated/feature-minicc-cloud` |
| `consolidation/read-failure-chain` | 1 (`ca872c9`) | **已进 main**：该提交是手工 3-way 单亲整合（非 merge），产物 `_AUDIT_RECOVERY_BYTES`、`gitprobe.WORK_TREE_VERDICT_NO`、8 个 gate、web bundle 全在 main | `consolidated/consolidation-read-failure` |
| `consolidation/cost-snapshot-chain` | 0 | **已完全合入** | `consolidated/consolidation-cost-snapshot` |
| `consolidation/i18n-sampling-chain` | 0 | **已完全合入** | `consolidated/consolidation-i18n-sampling` |
| `archive/read-failure-chain-t566-t574` | 3 (`3c5c8cf`/`95d7143`/`9baf31d`) | **已进 main 且更强**：见 §2.1 | `consolidated/archive-read-failure` |
| `backup/local-line-batches70-75` | 2 (`669eae5`/`9bae790`) | **主体作废**：见 §2.2。整条线保留作历史参照，不合 | `consolidated/backup-local-lines70-75` |
| `dev/minicc-reliability-4ba3` | 51（无共同祖先，独立 `git init` 平面） | **车道接管完成**：见 §2.3。无整树合并 | `consolidated/dev-reliability-4ba3-plane` |

### 2.1 archive 的 3 个 `+` 提交

- `3c5c8cf`（not-recorded 与「我没看到」分两个词）：main 的 `minicc/changes.py` 有 `PREIMAGE_NOT_IN_WINDOW = "not-in-window"` 与 `_audit_window_truncated`，且已**演进为 byte-only 窗口 + `_AUDIT_RECOVERY_BYTES=65536` 回读整条被切记录**——比归档分支的「字节 or 行」判据更强。门测试 `test_a_copy_line_the_window_never_reached_is_not_a_copy_that_was_never_recorded.py`（377 行）在 main。
- `95d7143`（test-only：subprocess 捕获加 `encoding/errors`）：main 全仓已是通用惯例，无产品差异。
- `9baf31d`（面板「没有数」印成 +0）：main 由 **M8-T774 按现役 web 架构重新实现**——`web/src/chat/stream.js::countLabel`、`web/src/core/i18n.js` 的 `changes.uncounted`（zh「数不出」/en「not counted」）、`web/src/files/preview.js`；门 `test_the_panel_does_not_print_a_missing_count_as_zero.py`。归档分支的整文件替换打法在 main 重写后的 UI 上已不适用，功能以新实现落地。

### 2.2 backup 的 2 个 `+` 提交（不合并）

- `669eae5`：标题虚高（声称改 router.py/pytest/caplog），真实 diff **只有 `minicc/config.py` + `minicc.config.example` 共 13 行**，加了个从无消费者的 `sampling_enabled` 配置骨架。`docs/INTEGRATION_STRATEGY.md` 已明确判「不合，保留作历史参照」，MCP sampling 的安全模型尚未设计。
- `9bae790`：34 文件 +4839 的整条 local batches 70-75 快照。main 用自己的 batches 70-91（同 task id）重做了功能；新文件已由 M8-T811 合入。主体作废。

### 2.3 dev 独立平面（51 提交，无 merge-base）

与 main 无共同祖先（独立 `git init`，657 文件），因此**不做整树合并**。逐文件对账确认已车道接管：MENTION 判决发射源（`minicc/mentions.py`、`test_a_mention_verdict_reaches_the_model_without_an_injection.py` 在 main 为 410 行 > dev 196 行）、`_newline_index` 换行尺（`scripts/doc_pointers.py`）、宽面名册（`tests/fence_rosters/wide.txt`）、T551-T562 各判据均在 main。抽查最近 8 个提交的核心标识符全部有 main 落点。

## 三、23 个测量平面 worktree 的处置

`wt*`/`plane*` worktree 是举证用的**冻结检出**，不是一个待合并的开发分支。22 个 HEAD 已在 main 历史：

```
plane195 plane196 plane_sdist wt353 wt353f wt354 wt379 wt463 wt463arms
wt470 wt470par wt478par wt517f wt519pre wt520old wt521a wt521c wt521d
wt529 wt537 wtfence379 wtrec353
```

唯一例外 `t544-plane`（`05dfa9b`，43 提交不在 main 历史）：核对发现 `git diff --name-only main...05dfa9b` 对 `minicc/`、`web/src/` **返回空**——这 43 个提交只改 `docs/ROADMAP_TO_PRODUCT.md` 的私有记录与若干门测试，生产代码零差异，属 dev 独立平面的 KI-543 checkpoint。**保留不删**：删除 worktree 等于销毁测量证据；它们已从开发职责退场，不再作分支使用。

归档在 `C:/Users/18414/.qoder-cn/scratch/` 的 `plane-cloud`/`plane715`/`plane716`/`plane718` 同理，对应分支已打 tag。

## 四、方法可复现（复核命令）

```bash
# patch-id 差集（- = main 已有等价，+ = 需人工看）
git cherry -v main archive/read-failure-chain-t566-t574
git cherry -v main backup/local-line-batches70-75
# 无共同祖先核验
git merge-base main dev/minicc-reliability-4ba3   # 退出码 1
# 独立平面的生产代码差异（应为空）
git diff --name-only main...05dfa9b | grep -E '^minicc/|^web/src/'
# 集大成 tag
git tag -n1 'consolidated/*'
```

## 五、边界

- 本轮**未**删除任何分支或 worktree——按要求"汇集所有内容"，证据完整性优先于减负；归并结论由 tag 固化。
- `origin/main` 落后本地 2 个提交（T817/T820），未擅自推送到远端（需 SSH 凭据，且推远端属外部动作）。
- `docs/INTEGRATION_STRATEGY.md`、`docs/SERVICE_PLANE_PLAN.md` 早前的"车道接管/不合"决策是本报告的判据之一，未推翻，只补齐了逐提交的复核证据。
- 与正在进行的并轨会话并发：`minicc/agent/tool_policy.py`、`minicc/audit.py`、`minicc/tools/{git,__init__}.py` 等为对方未提交改动，本报告与 tag 均未触碰；审计期间工作区出现的所有未跟踪临时文件也未纳入。
