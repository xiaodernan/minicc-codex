# SpecProof 复用评估

评估对象：`specproof-reference`，来源 `https://github.com/xiaodernan/specproof`，当前克隆提交 `0d85586`。本地扫描得到约 1,832 个文件、793 个 Python 文件、约 124,305 行 Python。

## 它解决的问题

SpecProof 的主线不是 Claude Code，而是 AI 代码变更的独立验收：把需求编译成契约，在隔离的 Base/Head 环境中做真实运行、差分、变异测试和证据签发。`craft/` 还包含一个带计划、编辑、执行、门禁和验收的开发 Agent。

它依赖的产品级外围包括 LangGraph、FastAPI、MySQL、Redis、RabbitMQ、MongoDB、Elasticsearch、MinIO、Docker、Web SPA 和 VS Code 扩展。这些对验收平台合理，对本地单用户 coding agent 过重。

## 值得带走的部分

| 能力 | 价值 | minicc-codex 状态 |
| --- | --- | --- |
| `craft/editor.py` 的工作区路径约束、原子写入、备份、审计、唯一匹配 | 防止 Agent 误写和覆盖并发修改 | 已迁移到 `minicc/tools/editor.py` |
| `craft/tools.py` 的风险分级、参数校验、结构化结果、截断和脱敏 | 让工具失败可控、可解释 | 已迁移到 `minicc/tools/registry.py` 和 `schemas.py` |
| `providers/openai_compatible.py` 的单一重试归属、Retry-After 和 usage 解析 | 适配不同 OpenAI 兼容网关 | 已迁移到 `minicc/llm/openai_provider.py` |
| `providers/redaction.py` 和结果安全标签 | 防止工具输出直接泄露秘密 | 已合并到 registry |
| `craft/context.py` 的上下文压缩思路 | 长任务不会无限膨胀 | 已简化到 `minicc/agent/context.py` |
| `providers/toolcheck.py` 的一次修复重试 | 处理模型生成的坏工具参数 | 下一阶段候选 |
| `sandbox/runner.py` 的 Docker 隔离 | 运行不可信代码时必要 | 已重写为可选 `host` / `auto` / `docker` 执行器；Docker 不可用时强制模式拒绝回退 |
| MCP stdio 工具边界 | 让外部工具以显式配置接入 | 已实现 `.minicc/mcp.json` opt-in 桥接，外部输出标记为不可信 |
| 可恢复任务与 worktree 编排 | 长任务和并行修改需要独立生命周期 | 已实现内存后台任务、取消、批量并行和受约束 Git worktree |

## 不直接迁移的部分

- Verify 的契约编译、Base/Head 差分、证据胶囊和 Ed25519 证书：这是验收产品，不是 coding agent 的第一条链路。
- API、租户、计费、消息队列、Mongo checkpoint、ES/MinIO 投影：会引入大规模部署和运维成本。
- 完整 SpecCraft planner/executor/gates：可作为未来“计划审批/验证闭环”参考，但当前 agent loop 先保持可读、可调试。

## 代码与许可证注意事项

参考仓库的 `pyproject.toml` 声明 MIT，但当前克隆根目录没有单独的 `LICENSE` 文件。这里采用“借鉴接口和设计思想、重新编写小型实现”的方式，保留参考仓库原样用于研究；如果未来要直接复制较大代码片段或对外发布，先向上游确认许可证和版权边界。

## 当前仍然需要诚实保留的边界

- Docker 是可选的本地执行器，不是完整容器编排或安全证明；工作区仍然以读写卷挂载。
- MCP 目前只支持 stdio 和工具调用，不包含远端授权、资源订阅或完整协议覆盖。
- 后台任务使用进程内线程池；服务重启后任务历史和排队状态不会恢复。
- 批量并行任务是独立任务 fan-out，不是带共享上下文、监督器和合并器的完整 subagent 系统。
- 当前项目没有 OAuth、多用户隔离、云端协作、自动提交或生产级审计服务。

## 下一步优先级

1. 加 `toolcheck` 的坏参数一次修复重试和结构化事件日志。
2. 将后台任务持久化到 SQLite，并在服务重启后恢复可重试状态。
3. 加计划预览、用户批准、验证命令和更完整的结果合并器。
4. 视真实使用需求再考虑远端 MCP、Windows Job Object 和多用户权限。
