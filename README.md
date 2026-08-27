# minicc-codex

一个工作区受限、支持工具调用的本地 coding agent。目标是先做出可运行的 Claude Code / Codex 风格核心，再按真实使用反馈扩展，而不是复制一个包含大量平台基础设施的完整验收系统。

## 当前能力

- OpenAI 兼容模型接口，支持原生 tool calls；不支持 tool calls 的网关可降级到 JSON action envelope。
- `read_file`、`glob`、`grep`、`tree`、`git_status`、`git_diff` 只读工具。
- `write_file`、`edit_file`：工作区路径约束、原子写入、备份、审计、精确匹配和 digest 过期保护。
- `bash`：工作区内执行命令；默认每次写入/执行都请求确认，`--yolo` 才自动放行。
- Web 安全模式会自动放行经过严格命令过滤的 `pytest` 只读验证；写文件和其他命令仍需打开 `Changes allowed`。
- 可选 Docker 执行器：`MINICC_SANDBOX=auto` 检测 Docker，`MINICC_SANDBOX=docker` 在 Docker 不可用时直接失败，不回退到宿主机。
- 可选 MCP stdio 工具桥：读取工作区 `.minicc/mcp.json`，工具默认按不可信输出处理。
- Web 后台任务：持久任务队列、SSE 实时推送（断线自动降级轮询）、取消、重新运行和批量并行任务，避免浏览器请求被长时间模型调用卡住。
- Web 工作区中心：可切换任意本地目录，记录最近目录，并显示每个任务的父子关系、流式文本、tokens、上下文和压缩次数。
- Web 多模态输入：支持文件选择、拖拽和粘贴图片；图片以任务附件保存到工作区的 `.minicc/attachments/`，任务历史只保存元数据，恢复任务时再重建模型 payload。
- 任务详情与可观测性：日志可展开到沉浸式/全屏面板，工具轮次可折叠，阶段事件展示轮次、工具、状态和验证证据；历史任务可直接回到真实会话页面。
- `web_search`：只读联网搜索最新资料；结果带来源 URL、摘要和不可信数据标记。联网默认关闭，必须在当前任务显式打开 `allow_network`。
- 搜索适配层优先使用 Bing，DuckDuckGo 作为备用；带超时重试、短期缓存、反爬诊断和连续失败熔断，避免 Agent 原地重复空搜索。
- Git worktree 管理：在工作区旁的隐藏目录创建和移除受约束的 worktree。
- 流式输出、工具参数校验、结果脱敏/截断、LLM 重试、上下文压缩和 usage 估算。
- 上下文压缩在消息字符数超过 `MINICC_COMPACT_THRESHOLD`（默认 300,000）且可压缩消息多于保留尾部时触发；保留 system 规则和最近 6 条消息，并把旧内容收敛为结构化 checkpoint：任务目标、验收要求、文件路径、digest、验证命令、失败记录、工具统计和归档 hash。checkpoint 会合并到下一次压缩并写入 `AgentState` 快照；完整原文不默认回填，未被提取的细节仍可能丢失，需要重新读取或查看 trace。
- Agent 执行器带有阶段摘要、短进度输出、只读并行执行、多阶段恢复诊断和重复工具调用保护；重复路径会先复用安全读结果、采集 git/tree 证据并暂缓写入，再重新规划。
- 可观测 StateGraph 运行时：记录 intake / plan / inspect / implement / verify / repair / summarize 节点、trace、运行统计和可序列化任务指标。
- 固定 DAG 模板和有界调度：提供 inspect→summarize、inspect→implement→verify、parallel inspect→merge→implement→verify 模板，校验依赖、环和最大并发。
- 验证器驱动闭环：成功写入后自动运行白名单 pytest，失败最多按 `MINICC_MAX_REPAIR_ATTEMPTS` 回到 repair；验证结果、失败测试、建议和耗时都会写入任务快照。
- 证据驱动完成评估：验证器之后由独立 LLM completion judge 根据原始需求、工具 trace、修改证据和验证结果返回结构化 `complete` / `continue` / `blocked`；`continue` 会把缺失目标反馈给 Agent 继续执行，评估失败会先触发一次复查，不会直接标绿。
- 自动并行编排：运行时按需求复杂度和独立工作维度评分；达到阈值后自动创建 2-3 个只读侦察子任务，独立 session 并行执行，父 Agent 收集证据后继续原始实现与验证。任务中心仍保留显式批量入口作为高级控制面板。
- 推理强度支持 `low`、`mid`、`high`、`xhigh`、`max`；Web 设置可按任务切换，网关不支持时会逐级降档并在 trace 中记录原因。修改后会自动要求下一轮检查 diff 和验证。
- 受约束动态规划：复杂 Web 任务会先请求模型生成小型 JSON 计划，服务端校验节点数、依赖深度、并发宽度、重试次数和工具白名单；非法或不可用计划自动回退固定 DAG，并记录来源与原因。自动并行子任务仍使用确定性只读职责模板。
- 依赖感知修复、本地证据检索和阶段路由：优先定位与失败测试和已写入路径相关的证据，并按 inspect/implement/verify/review 阶段选择合适的请求策略，不会覆盖用户显式配置的模型。
- 任务可靠性基线：SQLite 历史、只读检查点 digest 校验、任务级联网授权、脱敏审计导出和离线 30 条评测 fixture。
- Web 体验：亮色/暗色主题持久化、阶段摘要与工具轮次折叠、长输出边界、仅在用户已接近底部时自动跟随，避免阅读历史时跳屏。
- 支持 `AGENTS.md`、`CLAUDE.md`、`MINICC.md` 或 `.minicc/instructions.md` 项目指导文件；内容只作为工作约定，不能覆盖系统指令和权限边界。
- 交互命令：`/help`、`/tools`、`/status`、`/clear`、`/exit`。
- 会话断点：`--session-id interview-1` 保存本地脱敏 checkpoint，`--resume` 继续。

运行与数据策略：

```text
# Web 和 CLI 任务没有总执行时间、模型轮次或工具调用数量上限。
# 任务会持续到模型交付、用户取消或服务进程结束；断流会自动恢复。
MINICC_MAX_REPAIR_ATTEMPTS=2
# 以下是数据保留/并发容量，不会截断正在运行的模型任务。
MINICC_TASK_HISTORY_LIMIT=24
MINICC_TASK_HISTORY_MAX_AGE_DAYS=30
MINICC_TASK_EVENT_LIMIT=768
MINICC_TASK_STREAM_LIMIT=16000
MINICC_TASK_USAGE_LIMIT=64
MINICC_TASK_COMPACTION_LIMIT=64
MINICC_TASK_QUEUE_LIMIT=32
```

运行测试请使用 `python -m pytest -q`；项目已在 pytest 配置中固定工作区导入路径，直接运行 `pytest -q` 也应得到相同结果。

## 启动

```powershell
cd D:\面试项目\minicc-codex
Copy-Item minicc.config.example .env
# 编辑 .env，填入 MINICC_API_KEY
python -m pip install -e ".[dev]"
python -m minicc.main --workspace D:\面试项目\minicc-codex
```

一次性任务：

```powershell
python -m minicc.main --workspace D:\面试项目\minicc-codex "检查项目并补充测试"
```

Web 工作台：

```powershell
.\.venv\Scripts\minicc-web.exe --workspace D:\面试项目\minicc-codex --host 127.0.0.1 --port 8765
# 浏览器打开 http://127.0.0.1:8765/
```

Docker 执行模式（可选）：

```powershell
$env:MINICC_SANDBOX="auto"       # 有 Docker 就隔离，没有则保持 host
# $env:MINICC_SANDBOX="docker"   # 强制隔离；Docker 不可用时拒绝执行
.\.venv\Scripts\minicc-web.exe --workspace D:\面试项目\minicc-codex --port 8765
```

MCP stdio 配置示例（可选，保存为 `.minicc/mcp.json`）：

```json
{
  "servers": {
    "docs": {
      "command": "node",
      "args": ["path/to/mcp-server.js"],
      "read_only": true
    }
  }
}
```

后台批量任务接口：

```powershell
$body = @{ messages = @("分别检查 Python 测试", "分别检查前端结构") } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8765/api/tasks/batch -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod http://127.0.0.1:8765/api/tasks
```

接口默认按本项目当前面试网关配置：

```text
MINICC_BASE_URL=https://api.247kan.com/v1
MINICC_MODEL=gpt-5.6-terra
```

 也可以换成其他 OpenAI 兼容网关。带完整路径的 endpoint 会原样使用；只有裸 API 根地址才会自动补 `/v1`。

推理强度可以通过环境变量或 Web 工作台顶部的“推理强度”按钮（也可在设置面板）调整：

```text
MINICC_REASONING_EFFORT=high
```

模型请求会原样发送 `reasoning_effort=low|mid|high|xhigh|max`；如果兼容网关不接受该参数，Provider 会依次降档，最后关闭该扩展参数并继续请求。

离线评测和审计导出：

```powershell
python -m minicc.benchmarks --json-out output\\evaluation.json --markdown-out output\\evaluation.md
Invoke-RestMethod http://127.0.0.1:8765/api/audit?limit=500
```

评测命令只生成报告骨架和 30 条脱敏任务 fixture，不会伪造真实模型的成功率、延迟、token 或费用；接入模型运行时再填入原始结果。

断线后继续：

```powershell
.\.venv\Scripts\minicc.exe --workspace D:\面试项目\minicc-codex --session-id interview-1
.\.venv\Scripts\minicc.exe --workspace D:\面试项目\minicc-codex --session-id interview-1 --resume
```

## 参考仓库评估

`D:\面试项目\specproof-reference` 是从 `xiaodernan/specproof` 克隆的只读参考副本。具体取舍见 [docs/SPECPROOF_ASSESSMENT.md](docs/SPECPROOF_ASSESSMENT.md)。当前判断是：复用其工程边界思想和小块算法有价值，直接搬整个平台没有价值，复杂度会把一个本地 agent 变成分布式验收产品。

## 面试讲解与公开调研

实现取舍和验证证据见 [docs/AGENT_RESEARCH.md](docs/AGENT_RESEARCH.md)。核心可以这样讲：模型负责判断，Agent harness 负责上下文、工具、权限、并发、取消、重试、持久化和验证；实时 UI 展示的是可审计的阶段摘要和工具结果，不是模型的私有思维链。

完成判定的关键链路是：

```text
模型执行工具 -> Verifier 收集客观证据 -> completion judge 评估原始目标
                                      | continue
                                      v
                              Agent 继续工具循环
```

judge 只输出短依据、缺失项和下一步，不输出模型私有思维链；完成评估本身的 token 和 trace 也会进入任务快照，便于面试演示和失败复盘。

## 当前边界

这是本地 MVP，不等同于 Claude Code 或 Codex 的完整产品。Docker、MCP、后台任务、批量并行任务、自动复杂度路由、结果合并、SQLite 任务历史和 Git worktree 已提供可运行的本地实现，但仍有明确边界：SQLite 不是 Redis/分布式队列；服务重启会把运行中的任务标记为 `interrupted`，只能通过重跑继续，不能声称是精确的模型调用断点续跑。只读且 digest 未变化的检查点可复用事实提示，但写入任务或工作区变化后必须重新检查。模型 planner、repair scope、本地检索和阶段路由目前是受约束的初版；只读、审查和受限验证计划可以进入白名单 DAG 并行执行，含写入节点或不满足只读约束的计划仍只作为主 Agent 提示；尚无真实模型对比基线或 CI 指标；MCP 只支持 stdio；Docker 需要本机已安装并可用，工作区仍以读写挂载；RAG、OAuth、云端协作、自动提交和生产级多用户权限审计尚未接入。`bash` 在 host 模式仍然是本机子进程，运行不可信仓库时应使用 `MINICC_SANDBOX=docker` 并在隔离环境中使用。

Web 界面的权限开关默认是完全访问，适合本地面试演示；关闭开关可恢复当前任务的只读保护。服务端设置 `MINICC_YOLO=1` 会自动放行所有写入和命令工具，CLI 的 `--yolo` 也会启用同样模式。完全访问模式只应在你信任的本机工作区中使用。
