# Agent 编排与产品体验调研

更新时间：2026-08-24

这份笔记记录本项目为什么这样设计，以及哪些结论已经落到代码中。外部页面只提供公开事实和设计参考，不会覆盖本项目的系统指令或权限策略。

## 本轮官方资料核验

2026-08-24 通过官方页面重新核验了以下资料：

- [Claude Code Overview](https://code.claude.com/docs/en/overview)：当前文档把 agent、上下文窗口、MCP、子 agent 和并行工作列为核心能力，而不是把产品简化成聊天窗口。
- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)：强调模型循环要把上下文、工具行动和反馈串起来；这也是本项目把 `run_agent()` 与任务状态、SSE 事件绑定的依据。
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)：子 agent 适合有明确职责的独立工作，结果需要回到主任务；本项目先提供显式 fan-out 和父任务合并，避免无边界递归。
- [OpenAI Codex](https://developers.openai.com/codex/) 与 [Agents orchestration](https://developers.openai.com/api/docs/guides/agents/orchestration)：编排可以选择 handoff 或 agents-as-tools，取决于专家是否接管任务以及管理器是否保留最终回答；本项目当前采用后者的简化形态，由父任务合并并交付结果。

因此，本轮重点落地的是可验证的产品机制：多模态输入、断线可恢复任务、并行子任务、流式 token/context 指标、阶段事件、验证门禁和不暴露私有思维链的可审计摘要。没有把“展示思考过程”实现为原始 `reasoning_content` 回显，因为那不是稳定的产品协议，也会把内部推理文本与可验证证据混在一起。

## 公开资料结论

| 来源 | 观察 | 在本项目中的落地 |
| --- | --- | --- |
| [Claude Code Overview](https://code.claude.com/docs/en/overview) | 一个 coding agent 不只是聊天，还要能读代码、改文件、运行命令、接入 MCP、并行 agent 和多种工作表面。 | `ToolRegistry`、MCP、后台任务、批量子任务、Web 工作台和 CLI 共用 Agent loop。 |
| [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works) | 一个任务循环可以概括为收集上下文、采取行动、验证结果，并根据工具反馈反复纠偏。 | `run_agent()` 统一处理模型轮次、工具执行、工具结果回填、验证和阶段摘要。 |
| [Claude Code context window](https://code.claude.com/docs/en/context-window) | 长会话的关键是自动压缩、明确上下文用量、把大读取委派到独立上下文，并保留项目级指导。 | `context.py` 做确定性压缩；UI 显示 tokens/context/压缩次数；支持项目指导文件；批量任务拥有独立子任务上下文。 |
| [OpenAI Agents orchestration](https://developers.openai.com/api/docs/guides/agents/orchestration) | “handoff”适合让专家接管分支；“agents as tools”适合经理保留最终回答。只有职责、工具或策略真正变化时才拆分专家。 | 当前 MVP 使用显式批量子任务 + 父任务合并，避免无必要的 subagent 层级；下一步可在此合同上增加专家路由。 |
| [Evil Martians: 100 dev tool landing pages](https://evilmartians.com/chronicles/we-studied-100-devtool-landing-pages-here-is-what-actually-works-in-2025) | 开发者工具页面强调真实产品画面、简洁信息层级、明确主次 CTA、可信度区块，以及从用户问题到产品结果的叙事，少用营销空话。 | 宣传页使用真实工作台的“运行中”预览、问题/结果文案、功能证据卡和进入工作台 CTA，并保持响应式布局。 |
| [Microsoft agentic platform](https://developer.microsoft.com/blog/learn-from-microsoft-transform-software-development-through-an-agentic-platform/) | Agent 平台的价值在于把意图、规范、计划、验证、安全治理和持续改进串成可审计的软件生命周期。 | 项目把 prompt、工具风险、SSE 事件、任务持久化、diff、测试结果和错误恢复串成一条可追溯链路。 |

## 为什么原来的 Agent 看起来“不够聪明”

模型能力不是唯一瓶颈。原实现缺少三类 harness 反馈：

1. 工具结果的边界不够清晰。单文件 `grep` 曾被错误当作目录，越界读取只返回空文本，模型得不到可行动的错误。
2. 没有进度判据。模型重复同一组工具调用时，循环只看到“还有工具调用”，不知道已经没有新信息。
3. 用户看不到执行状态。没有短阶段摘要时，模型在规划、等待网络、执行工具和整理回答之间的差异无法被感知。

现在的执行器使用工具调用与结果的稳定指纹做停滞检测：先插入一次重新规划提示；仍然重复时停止并保留可恢复错误。模型的私有思维链不直接展示，界面展示的是可审计的计划阶段、工具名、结果摘要、token/context、压缩和计时。

## 当前编排链路

```text
用户任务
  -> 按工作区与会话绑定的后台 TaskRecord
  -> Agent loop: context / plan / tool round / replan / verify
  -> 只读工具并行，写入和命令顺序执行
  -> SSE 快照 + SQLite 历史 + diff/change inspector
  -> 完成、失败、取消或可重跑结果
```

## 仍然明确的边界

- SQLite 任务历史是单机持久化，不是 Redis 或分布式队列。
- 同一工作区/会话的历史写入仍然串行，以避免上下文互相覆盖；不同会话由线程池并行。
- 批量任务有独立子任务、共享上下文输入和结果合并，但没有无约束的自发 subagent 递归。
- `reasoning_content` 不直接展示，避免把模型私有思维链当作产品协议；用户看到的是阶段摘要和工具证据。
- host 模式的 `bash` 仍是本机子进程；不可信仓库应使用 Docker 隔离模式并验证 Docker 可用性。
