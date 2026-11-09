# 一个事实一个家 —— minicc-codex 的同一事实自律法（导览与守则）

本文是 minicc 的**元文档**：它不描述产品面，而是把这个仓库里最重要、且有反复纪录的开发行为——「同一个事实，只允许一个家」——整理成可读的地图与自检表。读它，能和它一起长出来的 M8-T6xx 系列的每一个批次，逐篇对账。

写于合流批 M8-T672 落定之后；合流决议（批次 668/669–671）记录在 `docs/ROADMAP_TO_PRODUCT.md`，冲突订正方法也在那里。

## 1 一条公理

> 任何数据、判词、状态、名字，**只许一个家**。家不是某个文件里的常量表，而是「谁负责改它、谁负责读它、谁负责钉住它」的三件套。

家的含义是三层逐条确定的：

1. **家**（home）：常量所在模块（不一定是定义点，也可以是它主导的权威来源）。
2. **读者**（readers）：任何模块要引用该家，不得自己手拼字面量——哪怕一次。
3. **门**（gate）：自动判定「没有人绕过这个家」的测试。

字面量过渡期必然会出现在代码里一小会儿（迁移批次的 Red→Green 之间），**提交前的门亮必过**。

## 2 为什么是这条公理

合流前，两条通道分别把同一套字典写了两遍、三遍，甚至二十遍——然后它们开始漂移：

- Mention 状态词（`injected`/`rejected`/`omitted`）曾经在两个模块里各写各的；XML 硬化「属性转义」和「整块折叠」也是两套实现。XML 硬化落到了一个家，XML 家门从「形状描述」演变为「替换外来拼写」——批 M8-T663 把它钉住。
- `task_manager` 里的 `“running”`/`“failed”`/`“interrupted”` 曾经全是手拼字符串，与 `agent.protocol` 的 `TASK_STATUS_*` 并列存在；这套字面量每漏一处，就给状态机漏一处 validation 短路。
- `audit_deletion_preimage` 的失败措辞在 agent loop、snapshots.py、changes.py 三处手拼出三套说法，最终由 gitprobe 收敛——批 M8-T648/550 系列。
- `SANDBOX_MODES`（`{"host", "docker", "auto"}`）只有 validator 消费；产品侧所有比对都是手拼 `== "host"` / `== "docker"` / `== "auto"`，所有检验都没有家；南反面曾有一处被 CI 抓，修了还是红，直到整个词表归家——批 M8-T679（`SANDBOX_MODE_*`）。
- `stage` 的六个词（`inspect`/`planning`/`implement`/`verify`/`repair`/`review`）在 `router.py`、`main.py`、`web.py` 各自硬拼；门住在 `tests/test_the_stage_names_have_one_home_in_the_tests_too.py`，产品侧并没有任何门——批 M8-T674。

字面量成批迁移，每次都是先**红先绿**（gate 先抓红，修，绿）。

## 3 这个仓库里，谁负责什么（同一事实家索引）

按"词表域"列举（**权威定义**在左列，**门**在右列）：

| 词表域 | 家 | 门（tests/） |
| --- | --- | --- |
| `TASK_STATUS_*` / `PHASE_*` / `TASK_KIND_*` | `minicc/agent/protocol.py` | `test_the_task_*_have_one_home*`、`test_the_task_phases_have_one_home.py` |
| `RESULT_FIELD_*` | `minicc/task_contract.py` | `test_task_result_*_field_has_one_home.py` |
| `VERIFICATION_STATUSES` / `NON_FAILURE` / `UNUSABLE` | `minicc/agent/verifier.py` | `test_the_verification_statuses_have_one_home.py` |
| `NODE_STATUS_*`（DAG 节点生命周期） | `minicc/agent/graph.py` | `test_the_dag_node_statuses_have_one_home.py` |
| `DAG_KIND_*`（DAG 任务种类） | `minicc/agent/graph.py` | `test_the_dag_node_kinds_have_one_home.py` |
| `FAILED_NODE_STATUSES` / `SUCCESS_STATUSES` | `minicc/agent/graph.py` | `test_the_failed_node_statuses_have_one_home.py` |
| `STAGE_*`（路由阶段名，也绑定 CLI choices） | `minicc/config.py` | `tests/test_the_stage_names_have_one_home_in_the_tests_too.py` 与 `tests/test_the_stage_names_have_one_home_in_the_product_too.py` |
| `SANDBOX_MODE_*` / `SANDBOX_BACKEND_UNAVAILABLE` | `minicc/config.py` | `test_the_sandbox_modes_have_one_home.py` |
| `HOOK_FAILURE_CONTINUE` / `HOOK_FAILURE_ACTIONS` | `minicc/hooks.py` | `test_the_hook_failure_actions_have_one_home.py` |
| `HOOK_DECISION_*` / `HOOK_EVENT_*` | `minicc/hooks.py` | `test_the_hook_{decisions,event_names,entry,denied_default}_have_one_home.py` |
| `PERMISSION_RULE_VERDICT_*` | `minicc/permissions.py` | `test_the_permission_rule_verdicts_have_one_home.py` |
| `MENTION_STATUS_*` | `minicc/mentions.py` | `test_the_mention_statuses_have_one_home.py` |
| `TOOL_STATUS_*` / `TOOL_NAME_*` | `minicc/tools/schemas.py` / `minicc/tools/names.py` | `test_the_*_tool_*_have_one_home.py` |
| `WORK_TREE_VERDICT_*`（git 判词） | `minicc/gitprobe.py` | `test_the_work_tree_verdict_kinds_have_one_home.py` |
| `COMPLETION_STATUSES` | `minicc/agent/completion.py` | `test_the_completion_verdict_*_have_one_home*` |
| `PERMISSION_MODES` | `minicc/audit.py` | `test_the_permission_modes_have_one_home.py` |

（新增词表时：先在家里常量化，门里对照（这一轮的 checklist 见 §5。）

## 4 门的写法（这个仓库一直沿用的形状）

门必须**机械可检查**，不靠人读。通常有三条腿：

1. home 必须当即定义给定的常量集合（`assert graph.NODE_STATUSES == frozenset(...)`）。
2. 全范围（`minicc/*.py`，常量按定义点之外、分机制豁免）不允许存在拼写该词的 `ast.Constant` / 成员集字面量——门要能被 AST 机械读到。
3. 出了门也要归位——读者模块只准走一刀（理想是门直接命中每行 `x = "failed"`，不靠人扫描）。

命中之后的归档是**可提交、可机判**的：门逻辑写入门文件、门文件入库、`--check` 出口 0。

Red 先于机械修改：在同一个提交之前呈现至少一条红，或是机器门先红后绿——合流红修（批 671/672/677/682）都是在这个次序上定下来的。

## 5 合流红修速查（拿走就能用）

这个仓库的合并优先级卡在「CI 红不红」，不是本地过没过。落地顺序：

1. 第一轮 `gh run view <id> --log-failed`：把 failing 测试逐条分账——归因（**不是负载**）或记入现任批次。
2. 每个红条目单独一个提交（或至少单独归因到它所在的批次）。
3. 提交前：`python scripts/doc_pointers.py --check` 必须出口 0；文档里同一持久事实只能出现一次。
4. 推送时候必须有 CI 全绿。
5. 红修单独成批次（或并入当批红色块），批号自增；门先宽后窄。

合并红修实例见：批 671（M8-T671，两条红）、批 672（M8-T672，两条 census 红）、批 677（`STAGE_REVIEW` 死 import）、批 682（census 门解常量）。

## 6 这条公理的反模式（不要走的路）

- **手拼字面量 + 只在注释里写「见某某常量」**：注释不约束精神，语义约束。
- **把一个原语词表在新模块里「重新定义一遍，fetch 省事」**：fetch 不是理由——家就是为这件事发明的。
- **用同一地址给合作者/外部用户都开引**："就这一次"的 hand-word 每次都会被下一个人复制。
- **改家为了迁就盗读者**：家是真，外面来迁就家——阅读者应当读家的名字，不应查找整行再造一套字义。

## 7 新人起步路线

1. 顺着 `docs/ROADMAP_TO_PRODUCT.md` 最近一批批次从 672 往回读（2026-11 起的全部合流/批次记录，M8-T673 ~ M8-T682）。
2. `python scripts/doc_pointers.py --check` —— 它能当场告诉你这个仓库目前知道多少持家词表、多少篇文档在读它们。
3. 选一个近门（如 `tests/test_the_stage_names_have_one_home_in_the_product_too.py`）去读它的腿——这是门写法取值的第一手。
4. 遇到跨模块引用某词表时，先查这个家索引表（本文 §3）；查不到就是值得问的事实，不是任由你写的字面量。

## 8 这个体系的边界（收口咽喉）

- "显不显成"——家是**单字**裁决者：某词表归属读者不多于 docs；门读者多于 docs 但仍只能扩 scope、不能取消契约。
- 家**不能**包办所有「同类」——lexical 相同的词如果承载不同裁决（如 `pass`"测试"结果vs `PASS = 0` exit-status），它们是不同的事实，必须保持分家。
- 门不是百万投机：是的，不少红修看起来纯属 self-inflicted（census gates 解常量），这是权力：它保护「同一事实不能有两个家」，为此牺牲门的单纯速度。

## 9 验收 —— 这个家学得怎么样

在你不用这些规则的那一年内：如果合流所有 doc/CI/batch 的提交记录里能找出**任何一个同词异义**，要么是在更早的真品里（已经查证记录在册），要么是错了，要么——就像本规则——是待推的 Gate。
