# 可复现的定向行为评测

`behavior` 套件包含 12 个小型 Python 修复任务，每个任务在独立临时 Git 仓库运行。评分器位于工作区之外，检查边界值、异常类型和输入不变性；布尔结果不接受以整数冒充。它衡量这些行为样本的完成能力，不代表所有真实工程任务的准确率，也不是对抗性沙箱。

只生成报告，不调用模型：

```powershell
.venv/Scripts/python.exe -m minicc.benchmarks --suite behavior
```

针对指定样本使用当前配置的模型，避免每次执行全部样本：

```powershell
.venv/Scripts/python.exe -m minicc.benchmarks --suite behavior --run --task-id behavior-median --task-id behavior-parse_bool --task-timeout 360 --results output/behavior-targeted-results.json --json-out output/behavior-targeted-report.json --markdown-out output/behavior-targeted-report.md
```

`--task-id` 可重复使用；未知 ID 会在调用模型前报错。`--max-tasks` 在任务选择之后限制数量。`--no-resume` 强制重新执行所选任务。

续跑只复用同一任务、fixture、运行时源码、Git revision、配置及超时时间的已完成记录。配置指纹不包含 API key，报告不会记录 endpoint 明文。不同配置或代码的旧行会从当前结果集中移除，未重新执行的样本报告为 `not_run`，不会混入新版本准确率。

每个任务结束后，结果先写到同目录临时文件，刷盘后原子替换，避免中断把之前完成的 JSON 截断。Ctrl+C 会先记录当前任务为 `interrupted`、发送取消并保存之前的结果，再退出。任务超时会发出取消并等待最多 5 秒；如果 SDK 仍未退出，整轮停止派发后续任务，后台等待该调用结束后再关闭服务。Python 线程不能强制终止，仍在运行的 fixture 目录会保留，并在结果中记录 `retained_workspace`。这意味着超时限制的是评测等待和后续派发，不是对外部服务强制断开请求的保证。

指标说明：

| 指标 | 含义 |
|---|---|
| `execution_completion_rate` | 执行流程正常结束的比例 |
| `grading_coverage` | 已运行样本中具备评分结果的比例 |
| `acceptance_success_rate` / `pass_at_1` | 有评分样本的独立验收通过率；不把未评分样本算成通过 |
| `false_completion_rate` | 有评分样本中，宣称完成但验收失败的比例 |
| `tokens_per_success` / `cost_per_success_usd` | 所有运行（包含失败）的开销除以成功数；任一运行缺测时为 `null` |
| `execution_latency_ms` | fixture 准备及模型执行耗时 |
| `grading_latency_ms` | 独立评分耗时 |
| `latency_ms` | 从任务开始到评分结束的总耗时 |

费用没有可靠来源时维持 `null`；fake provider 结果带元数据标识，仅用于协议和流程验收。不要将 fake 结果或本仓库的单元测试通过率描述为真实模型准确率。

明确取消的结果记录为 `cancelled`；完成评估返回 continue/blocked/unknown 等结果时记录为 `incomplete`，不运行 grader 来伪装完成。评分器自己跑不起来（异常、超时、退出码 2）记录为「判不了」（`passed=null` + `grading_refused`），不计入通过率分母；宿主写不出 fixture（磁盘、权限、`git init` 超时）同样记「判不了」，因为那是宿主的账，不是智能体的判决。Ctrl+C 中断当前任务时先落一条 `status=interrupted` 的「判不了」行（操作员的账，不是智能体失败），再把中断抛出去；诊断用 oracle 不会在中止时重跑。fixture 清理失败保留路径供检查。失败运行的 token 同样计入每次成功的总成本，不能只统计成功样本的花费。

评测器定向检查：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_benchmark_runner.py tests/test_behavior_bench.py -q -o addopts=''
```

2026-09-29 复现结果：上面「评测器定向检查」命令输出 `31 passed in 240.77s`。可比的读数是**条数**——它随这两套测试的用例数变化，务必以命令实际输出为准，不要手改本行；需要更新时请重跑该命令并原样回填。墙钟时间在同机并发时会大幅偏高（本次读数期间同一台机器上另有会话在跑），不要当作基线。`output/benchmark-hardening-checks.xml` 可留存 JUnit。没有运行全量回归或使用真实模型生成新的准确率结论。

## 可写工作区套件（v2，M4-T5 起）

`v2` 套件（`benchmarks/tasks.v2.json`，24 条任务，`suite_version: v2-1`）与 legacy 只读套件的本质区别：每条任务带 `fixture`（内联声明的若干文本文件），评测在**隔离临时工作区**里以 `allow_changes=True` 跑智能体——编码能力才真正被测量，写权限才可能安全开启。评分器（oracle）分两种：

- `file_contract`：按文件检查 `exists` / `contains` / `not_contains` / `equals` / `regex` / `json_equals`。契约路径逃逸工作区、或目标文件不是合法 UTF-8 时，评分器拒绝判决（exit 2 =「判不了」），不在替换字符上凑答案。
- `command_contract`：在工作区里跑一条命令（通常是仓库自己的测试），检查退出码（`expect_exit`）与 stdout 标记（`stdout_contains`），默认超时 180 秒。`{python}` 占位符由宿主侧渲染（带空格的解释器路径不再被 shell 拆碎）；评分环境固定 `PYTHONDONTWRITEBYTECODE=1`（防陈旧字节码在同 mtime 文件系统上遮住智能体的修复）与 `PYTHONIOENCODING=utf-8`（防 cp936 宿主把中文标记读成乱码，M8-T58 实测）。

评分驱动脚本物化在**仓库之外**的 `.graders` 目录（`MINICC_EVAL_GRADER_DIR` / `--grader-dir`），智能体的文件工具读不到它；期望值留在 `tasks.v2.json` 里，永不进入被测工作区。同类型所有任务共享两个脚本名（`file_contract.py` / `command_contract.py`），跨进程评测会竞写——物化是「写 per-writer 临时文件 + `os.replace` 原子替换」（M8-T157），并发子进程永远不可能 exec 半写脚本；竞争退避耗尽时干净地以 `grader_unable` 拒绝评分（宁可判不了，也不执行错代码）。

任务文件在加载期全量校验（`validate_task`）：必需字段齐全、`suite_version` 可识别、prompt/category 非空、fixture 键不逃逸也不互占位置（含大小写与父目录冲突，`os.path.normcase` 按段比较）、grader 类型与规格可执行、`max_minutes` 为正——坏任务文件在**为智能体付费之前**报错，而不是退化成一条没人判分的记录。

骨架报告不调模型：

```powershell
.venv/Scripts/python.exe -m minicc.benchmarks --suite v2 --json-out output/v2-skeleton.json --markdown-out output/v2-skeleton.md
```

定向真跑（配额允许时）：

```powershell
.venv/Scripts/python.exe -m minicc.benchmarks --suite v2 --run --task-id v2-greeting-already-correct --task-timeout 900 --json-out output/v2-probe.json --markdown-out output/v2-probe.md
```

2026-10-07 骨架门实测：同命令（输出名不同）exit 0，`fixture_count=24`。真实模型读数待网关配额对真实 agent 负载恢复后回填——当前单条真任务在 171s 后仍遇 429，报告如实记 `infra_failure_count`，不把网关故障算成模型失败（见下）。

基础设施失败语义（M8-T154）：错误以「LLM 调用失败」开头的行（provider 429 / 连接错误）计入 `infra_failure_count`，不与模型真失败混算；`pass_at_1_ex_infra` 把它们从分母排除，排除后分母为空时如实 `null`，不假 100；`pass_at_1` 分母冻结不动（历史可比）。`bench_compare --gate` 的门槛认 `pass_at_1_ex_infra`（M8-T155），配额停电不再把 A/B 变体判死。

## 检索决策门（M4-T7，2026-09-21）

`minicc/agent/retrieval.py` 是确定性的 token + path + symbol 词法打分，自述「不是向量数据库」。M4-T7 不直接上 embedding，而是先用「已知答案定位」数据集 `benchmarks/retrieval-hitrate.json`（20 条，每条 = 开发者提问 + 应答的仓库相对文件）量化词法基线，指标为 `recall@k = |targets ∩ top-k| / |targets|` 按 case 求均值，MRR 取首个命中目标排名倒数。复现命令：

```powershell
.venv/Scripts/python.exe -m minicc.benchmarks --suite retrieval --json-out output/retrieval.json --markdown-out output/retrieval.md
```

本轮基线（在本仓库自身上检索，2026-09-26 复跑；上一轮记录为 `recall@5=0.90`、`MRR=0.75`，差值在下文所说的抖动范围内）：`recall@1=0.65`、`recall@5=0.95`、`MRR=0.7683`、`cases=20`。
口径（M8-T72 起由报告自己带出来，键 `report["index"]`）：`files_indexed=232 / file_limit=1200 / files_seen=232 / files_skipped=0 / directories_walked=21 / directory_budget=4800 / truncated=False`，本次 `last_build_ms=804.46`（缓存已热）——也就是说遍历确实走完了整仓，上面四个数字是关于本仓库的陈述，而不是关于它某个前缀的陈述。

**书面结论**：`recall@5=0.90 >= 0.60`（路线图设定的引入门槛），词法基线已能可靠定位已知答案，**不引入向量检索**，停止在 embedding 上的投入。该结论由 `tests/test_retrieval_eval.py::test_real_dataset_clears_floor_backing_the_written_conclusion` 守护——一旦数据集 `recall@5` 跌破门槛，测试即红，提醒重新评估；并由 `tests/test_index_census.py` 守住另一半：出这个数字的那次遍历必须确实覆盖整仓（`minicc/agent/retrieval.py::census_is_complete`），口径不完整时 `retrieval_decision` 两个分支都不给。CI 仅记录这些数值、不门禁（首轮只建基线）。注意 `recall` 受文件 mtime 新鲜度加权影响，跨机器可能在 ±0.05 抖动，但 0.90 对 0.60 的门槛有充足余量。

**为什么分母要写进报告（M8-T72 的实测）**：`LocalEvidenceIndex` 有两道预算——`max_files` 个候选文件，以及 `max(4000, max_files * 4)` 个目录——任何一道先到，指标就算在工作区的一个前缀上。在 `ac76061` 上量过：1250 个 `.py` 对 1200 的预算、目标文件排在切点之后，`--suite retrieval` 照样 exit 0，并且打出「lexical 基线不达标，下一步评估引入本地 embedding」——一次预算截断被读成了架构建议；反过来，4300 个目录、20 个文件全在目录切点之后（`max_files=900`，目录预算 `max(4000, 3600)=4000`）时，`stats()` 报 `files_indexed=0, truncated=false`，因为旧判据是 `len(records) >= max_files`，它恰好在这种「没填满预算」的截断上答反方向。现在 `truncated` 说遍历有没有走完，`files_seen`/`files_skipped` 说差多少，报告与 markdown 都带这一行。
