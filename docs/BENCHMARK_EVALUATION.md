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

明确取消的结果记录为 `cancelled`；完成评估返回 continue/blocked/unknown 等结果时记录为 `incomplete`，不运行 grader 来伪装完成。独立评分异常记录为失败，fixture 清理失败保留路径供检查。失败运行的 token 同样计入每次成功的总成本，不能只统计成功样本的花费。

评测器定向检查：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_benchmark_runner.py tests/test_behavior_bench.py -q -o addopts=''
```

2026-09-18 本轮结果：23 项通过（9.78 秒），`output/benchmark-hardening-checks.xml` 留存 JUnit；随后补充 Ctrl+C 中断保存与资源生命周期处理，runner 的 12 项定向检查再次通过。没有运行全量回归或使用真实模型生成新的准确率结论。
