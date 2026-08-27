# minicc：Agent / LLM 技术增强路线图

> 目标：在不把项目做成不可控的“多 Agent Demo”的前提下，补充有工程含金量、可量化验证、适合面试讲解的 Agent 编排能力。
>
> 原则：**先做可观测的单 Agent 编排，再做受约束的多 Agent；先建立基线，再报告提升。**

## 1. 当前项目基线

minicc 已经具备：

- OpenAI 兼容模型 + 原生 Tool Calls / JSON Envelope 降级。
- ReAct 式 Agent Loop：模型决策 → 工具调用 → 工具结果回填 → 继续决策。
- 只读工具并行，写入和命令顺序执行。
- 工具参数校验、权限确认、结果截断、敏感信息脱敏。
- 上下文压缩、停滞检测、一次自动重规划。
- SQLite 任务持久化、SSE 流式事件、取消、重跑、批量任务。
- Docker 沙箱、MCP stdio 桥、Git worktree。
- 当前测试基线：由 `python -m pytest -q` 在本地固定任务集上维护；本轮实现后为 `79 passed`。

当前主要缺口：

1. 自动并行路由仍使用确定性复杂度评分和固定只读职责；复杂 Web 主任务已经支持受 schema、依赖、并发和工具白名单约束的只读动态 DAG，写入型计划仍回退到主 Agent 的原有权限路径。
2. 没有统一的 trace、成本、延迟和质量评测数据集。
3. 现有固定 DAG、验证器和 repair loop 已闭环，但还没有按依赖分支增量重试和跨 worktree 的自动合并策略。
4. 上下文压缩仍缺少“按任务选择上下文”的检索与记忆策略；当前已先落地确定性的结构化 checkpoint，保留目标、验收、路径/digest、验证与失败证据，并明确未提取细节的丢失边界。
5. 模型、工具和验证器尚未按预算、风险、任务难度做完整的多模型路由。

## 本轮已落地（P0 最小闭环）

本轮已经把第一、第二阶段的核心运行时接入现有 Web 任务，不改变 OpenAI tool-call 协议：

- `minicc/agent/state.py`：`AgentState`、`TraceEvent`、`Budget`，记录节点、阶段、预算、证据、错误和可序列化 metrics。
- `minicc/agent/graph.py`：带条件转移和有限 repair 回边的 `StateGraph`，以及校验依赖、环、深度、节点数和并发的 `DAGPlan` / `execute_dag`。
- `minicc/agent/verifier.py`：只执行白名单验证命令，输出 `passed` / `failed` / `blocked` / `skipped` 结构化结果、失败测试和 actionable hint。
- `minicc/agent/planner.py`：解析模型生成的结构化计划，限制节点 kind、依赖、深度、并发、重试和工具白名单；失败时回退固定模板。
- 现有 `run_agent`：统一记录轮次、工具调用、token 和预算超限事件；Web 写入任务自动进入验证，失败最多按配置次数 repair。
- 批量任务：保存固定 DAG 模板、关键路径和最大并发信息；复杂请求的自动侦察仍限制为固定数量的只读子任务。Web 主 Agent 在复杂任务启动前会把模型计划作为受校验的公开上下文；满足只读约束时，动态计划会进入真实 DAG 节点执行，并记录节点状态、依赖摘要、planner token、来源和回退原因。

这部分是工程能力实现，不是性能结论。重复调用率、P50/P95、成本和长任务成功率仍需后续固定 benchmark 多次运行后再报告。

## 尚未声称完成的部分

- 当前没有让模型自由生成并直接执行任意 DAG；已经接入的是只读白名单内的受约束动态 DAG，写节点隔离、依赖节点增量恢复和跨 worktree 合并仍属于后续阶段。
- 当前没有接入向量数据库或不透明的长期记忆；上下文检索仍以已有确定性压缩和任务证据为主。
- 当前没有提交 baseline / enhanced 的 10~30 任务 benchmark 原始数据，因此路线图中的百分比仍只是目标格式。

## 2. 最值得补充的技术（按推荐顺序）

### P0：可观测的 StateGraph 编排层（已落地，可继续增强）

把当前循环拆成显式节点：

```text
intake
  -> plan
  -> inspect
  -> implement
  -> verify
  -> repair (失败时回到 implement)
  -> summarize
```

每个节点拥有：

- 输入 / 输出 schema；
- 最大 token、最大耗时、最大重试次数；
- 允许使用的工具集合；
- 成功条件和失败转移；
- trace span、耗时、token、工具调用数。

建议实现：`minicc/agent/graph.py`、`minicc/agent/state.py`。

面试价值：这不是“让多个 Agent 聊天”，而是把 LLM 当作非确定性决策节点，把确定性状态、权限、重试、取消和验证交给运行时控制。

可量化指标：

- 相同任务集下，工具重复调用率下降 **目标 20%~40%**；
- 因无效循环导致的失败率下降 **目标 15%~30%**；
- 平均任务完成时间、P95 延迟、每任务 token 和工具调用数可追踪；
- 以上数字必须通过 A/B 基准实测，不能直接当作结论。

### P0：DAG 任务规划 + 有界并行调度

不要让模型自由递归创建 subagent。让 planner 只输出结构化计划：

```json
{
  "tasks": [
    {"id":"scan", "kind":"readonly", "depends_on":[]},
    {"id":"tests", "kind":"readonly", "depends_on":["scan"]},
    {"id":"patch", "kind":"write", "depends_on":["scan"]},
    {"id":"verify", "kind":"exec", "depends_on":["patch","tests"]}
  ]
}
```

运行时负责：

- 校验 DAG 无环；
- 只调度依赖已完成的节点；
- 只读节点并行，写入节点按 worktree / 文件锁隔离；
- 限制最大深度、最大节点数和最大并发；
- 子任务失败时只重试失败分支，而不是重跑全图；
- 最终由 verifier 合并证据，不直接相信子 Agent 的自然语言结论。

可量化指标：

- `wall_clock = max(并行分支耗时) + 串行关键路径耗时`；
- 与串行基线比较，报告总耗时降低比例；
- 报告并发度、关键路径长度、任务失败重试次数；
- 目标：独立只读检查任务的 P50 耗时降低 **25%~50%**，具体取决于网络和磁盘瓶颈。

### P0：验证器驱动的闭环（Verifier / Repair Loop）

把“模型说完成了”改成“可验证证据证明完成了”：

```text
implement -> pytest / ruff / mypy / diff policy -> verifier
                                     | pass
                                     v
                                  summarize
                                     |
                                    fail
                                     v
                                  repair
```

验证结果采用结构化格式：

```json
{
  "status": "fail",
  "command": "python -m pytest",
  "exit_code": 1,
  "failed_tests": ["test_x"],
  "actionable_hint": "..."
}
```

安全边界：验证器只能执行白名单命令；命令输出当作不可信工具结果；修复最多 N 次；每次修复都保留 diff 和测试证据。

面试价值：可以讲“证据闭环”和“失败可恢复”，而不是只讲 prompt。

### P1：模型 / 策略路由（Model Routing）

按任务阶段和难度选择模型：

- `fast`：文件定位、目录扫描、格式化、短摘要；
- `balanced`：普通修改和测试修复；
- `reasoning`：复杂规划、疑难调试、跨模块修改。

路由输入可以包括：任务文本长度、文件数量、历史失败率、预计工具调用数、风险等级和剩余预算。

建议保留 fallback：模型超时、限流或结构化输出失败时，降级到备用模型或纯确定性工具流程。

量化指标：

- 成功率 / pass@1；
- 平均输入输出 token；
- 单任务成本；
- P50 / P95 延迟；
- fallback 次数和原因。

目标示例：在成功率不下降超过 1 个百分点的约束下，平均 token 成本降低 **20%~40%**。这是实验目标，不是现成结论。

### P1：上下文工程 2.0：分层上下文 + 任务记忆

当前 `compact()` 是按消息长度做摘要，下一步建议分层：

1. **固定层**：系统规则、权限边界、项目指导文件；
2. **任务层**：当前目标、验收标准、计划和失败记录；
3. **证据层**：最近工具结果、测试日志、diff；
4. **检索层**：按当前子任务召回的相关文件 / 符号 / 历史经验；
5. **归档层**：完整 trace，不默认塞回 prompt。

推荐先做确定性版本：文件路径 / 符号 / tool result 建索引，按任务关键词和依赖关系召回，不急于引入向量数据库。

指标：

- prompt token 数；
- 压缩次数；
- 召回文件命中率；
- 因上下文缺失导致的重复读取率；
- 长任务成功率。

目标：在长任务成功率不下降的前提下，平均 prompt token 降低 **30%~60%**。

### P1：持久化检查点与可恢复执行

当前 SQLite 主要保存任务快照。可以进一步保存：

- graph state；
- 已完成节点及输出摘要；
- 当前 checkpoint；
- 重试次数和预算消耗；
- workspace / worktree 版本标识；
- 可恢复的幂等工具调用记录。

恢复时从最后一个成功节点继续，而不是从头调用模型。

必须处理：

- 写入工具的幂等键；
- checkpoint 与文件 digest 校验；
- 服务重启后的 interrupted 状态；
- 外部网络工具不可重放时的结果缓存。

指标：断电 / 服务重启注入测试中，恢复成功率、重复工具调用数、恢复耗时。

### P2：受约束的专家 Agent

仅当职责、工具或策略确实不同才拆分专家：

- `Explorer`：只读扫描和依赖分析；
- `Implementer`：只能修改分配的 worktree / 文件范围；
- `Tester`：只能运行验证命令并解释失败；
- `Reviewer`：只读审查 diff 和测试证据。

Manager 负责计划和最终合并；专家不能无限创建新专家。

推荐两种编排模式：

- **Handoff**：一个专家把控制权交给另一个专家；适合职责切换；
- **Agents as tools**：Manager 调用专家并保留最终控制权；适合需要统一答案和预算的场景。

不要把“多个 Agent”作为目标，先证明它比单 Agent 在某类任务上更好。

## 3. 建议的最小落地版本

### 第一阶段：可观测运行时

新增：

- `AgentState`：任务、阶段、预算、上下文、证据、错误；
- `TraceEvent`：节点开始 / 结束、LLM、工具、验证、重试；
- `Budget`：最大 turns、token、耗时、工具调用数；
- `StateGraph`：节点、边、条件转移。

先把现有 loop 包装成图，不改变已有工具协议。

### 第二阶段：固定 DAG 模板

先不做完全自由规划，提供三个模板：

1. `inspect -> summarize`；
2. `inspect -> implement -> verify -> repair`；
3. `parallel inspect -> merge -> implement -> verify`。

这样容易测试、容易演示，也能量化并发收益。

### 第三阶段：结构化 Planner

让模型只生成 JSON 计划；服务端做 schema 校验、环检测、节点数限制和工具权限映射。非法计划直接要求模型修正，不进入执行器。

### 第四阶段：评测面板

增加 `benchmarks/`：

- 10~30 个固定 coding tasks；
- 每个任务有 workspace、目标、验收命令、预期文件；
- 运行 baseline 和 enhanced 两组；
- 输出 JSON / CSV / Markdown 报告。

## 4. 必须记录的指标

每个任务至少记录：

| 类别 | 指标 |
| --- | --- |
| 质量 | task success、测试通过率、patch correctness、人工审查分 |
| 效率 | 总耗时、P50/P95 延迟、LLM turns、工具调用数 |
| 成本 | prompt/completion/reasoning tokens、估算费用 |
| 并发 | 最大并发、关键路径、串行/并行耗时比 |
| 可靠性 | 重试次数、停滞触发、恢复成功率、取消响应时间 |
| 上下文 | 压缩次数、prompt token、召回命中率、重复读取率 |
| 安全 | 被拒绝的高风险调用、越界尝试、敏感信息脱敏数 |

推荐报告格式：

```text
任务集：30 个本地 coding tasks
Baseline：当前 run_agent
Variant：StateGraph + verifier + bounded DAG
Success：82% -> 90% (+8pp)
P50 latency：48s -> 35s (-27%)
P95 latency：160s -> 118s (-26%)
Tokens/task：18.2k -> 13.7k (-25%)
Repeated tool rounds：1.8 -> 0.9 (-50%)
```

上面的数字只是报告格式示例，不能当作 minicc 的实测结果。

## 5. 面试时可以这样讲

> 我没有直接堆递归多 Agent，而是先把 Agent runtime 做成受约束的状态图。LLM 负责规划和局部决策，运行时负责状态、依赖、权限、预算、并发、取消、checkpoint 和验证。只读任务可以在 DAG 中并行，写入任务按 worktree 隔离，测试失败会进入有限 repair loop。最终通过固定任务集对比 baseline，报告成功率、P95 延迟、token 成本、重复工具调用和恢复成功率，而不是只展示一次 Demo。

进一步追问时可展开：

- 为什么不让 subagent 无限递归？——不可控的成本、上下文和失败传播；使用最大深度、节点数、预算和权限边界。
- 为什么不展示 CoT？——产品展示可审计阶段和工具证据，不暴露模型私有推理内容。
- 如何保证并行安全？——只读并行；写入按 worktree / 文件锁隔离；合并前做冲突检查和测试。
- 如何证明优化有效？——固定任务集、固定模型和温度、baseline/variant A/B、多次运行、报告均值和 P50/P95。
- 如何处理模型不可靠？——结构化输出校验、工具结果 schema、verifier、有限重试、fallback 和可恢复 checkpoint。

## 6. 暂不建议优先做的方向

- 无约束的递归多 Agent：演示热闹，但成本和失败传播难控制。
- 一开始就接向量数据库：如果没有检索命中率和任务收益指标，容易变成架构装饰。
- 只增加更长的 system prompt：不能替代状态、验证和权限控制。
- 只用单次 Demo 宣称性能提升：必须有任务集和 baseline。
- 过早引入分布式队列：当前项目是本地单机 Agent，先把 SQLite checkpoint 和可恢复语义做扎实。

## 7. 参考资料

以下链接用于理解公开的 Agent 编排与 coding-agent 设计，不代表项目已完整实现对应产品能力：

- Anthropic — [Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- Claude Code — [Overview](https://docs.anthropic.com/en/docs/claude-code/overview)
- Claude Code — [How Claude Code works](https://docs.anthropic.com/en/docs/claude-code/how-claude-code-works)
- Claude Code — [Context window](https://docs.anthropic.com/en/docs/claude-code/context-window)
- OpenAI — [Agents orchestration](https://developers.openai.com/api/docs/guides/agents/orchestration)
- Microsoft — [Agentic platform for software development](https://developer.microsoft.com/blog/learn-from-microsoft-transform-software-development-through-an-agentic-platform/)
- SWE-bench — [Benchmark repository](https://github.com/SWE-bench/SWE-bench)
- LangGraph — [Durable execution](https://langchain-ai.github.io/langgraph/concepts/durable_execution/)

> 联网检索接口本轮未返回有效结果，因此没有把未经核验的论文排名、模型版本或公开百分比写成事实。真正实现后，应把基准脚本、原始运行数据和报告一并提交到项目中。
