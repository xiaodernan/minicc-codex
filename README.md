# minicc-codex

一个工作区受限、支持工具调用的本地 coding agent。目标是先做出可运行的 Claude Code / Codex 风格核心，再按真实使用反馈扩展，而不是复制一个包含大量平台基础设施的完整验收系统。

## 当前能力

- 双协议模型接口：OpenAI 兼容（chat_completions / responses + JSON envelope 降级）与 Anthropic 原生 Messages API（`MINICC_PROVIDER_TYPE=auto|openai|anthropic`，auto 按模型名/端点推断；Anthropic 可用 `MINICC_ANTHROPIC_BASE_URL` 指向独立网关，留空则复用 `MINICC_BASE_URL`）；Anthropic 路径自带 prompt caching（system 与工具集 cache_control 断点）与缓存命中归一化。
- OpenAI 兼容模型接口，支持原生 tool calls；不支持 tool calls 的网关可降级到 JSON action envelope。
- Web 服务安全基线：token 认证（`--token` / `MINICC_WEB_TOKEN` / 自动生成并持久化到 `.minicc/web_token.json`），非回环地址（`--host 0.0.0.0`）强制开启认证；CORS 仅放行本机回环来源；`MINICC_WORKSPACE_ROOTS` 可把可切换工作区限制在目录白名单内。
- 任务级权限模式：`default`（跟随写入/联网开关）、`plan`（只读规划，写与命令被拒）、`acceptEdits`（自动接受文件写入，命令仍需授权）、`yolo`（全部放行）；CLI 用 `--permission-mode`，Web 提交 payload 传 `permission_mode`。所有模式判定都进入审计事件。
- `webfetch` 工具：抓取公开网页正文转文本（SSRF 防护默认拒绝内网/回环地址，重定向逐跳校验；`MINICC_ALLOW_PRIVATE_FETCH=1` 可放开本机抓取），与 `web_search` 一样按任务级 `allow_network` 门控，输出标记为不可信。
- `todo_write` / `todo_read` 工具：模型维护结构化任务清单（持久化到 `.minicc/todos.json`，整体替换语义，同时只允许一项 in_progress），结构化数据随任务事件透传给前端计划面板。
- `task` 子代理工具：模型可派生受限的只读侦察子代理（独立上下文与预算；无写/命令/联网权限，不能递归派生；并发上限 3，超时与取消可控），结果以不可信工具结果回传。
- 任务历史全局搜索：`GET /api/history/search?q=&limit=&workspace=`，跨工作区检索历史任务的提示词、回答与流文本，返回匹配计数与上下文摘录（快照入库前已脱敏）。
- MCP 工具桥支持 stdio 与 streamable HTTP 两种 transport（`mcp.json` 服务器条目配 `command` 或 `url`，HTTP 支持 `headers` 鉴权与 `Mcp-Session-Id` 会话），外部工具输出默认按不可信处理。
- CI（GitHub Actions）：Windows/Ubuntu 双平台 pytest、前端 JS 语法检查、Playwright web smoke。
- 任务执行器双模式：`MINICC_TASK_EXECUTOR=thread`（默认，进程内）或 `process`（任务在独立 `minicc.task_worker` 子进程中执行，进度实时写入共享 SQLite，取消经标志文件传播，web 重启后 worker 存活不丢任务）；`MINICC_AUTO_RESUME_ON_START=1` 启动时自动重新排队被中断的任务（带心跳守卫防双跑）。
- 前端为 ES 模块构建产物：入口 `web/src/main.js`，按 transport、任务状态、时间线、面板和文件预览分层；`npm run build:web` 生成可调试 bundle 与带内容 hash 的压缩 JS/CSS，`npm run check:web` 校验新鲜度。小游戏按需加载，HTML 与资源别名使用 ETag 校验，版本化资源长期缓存。
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
- 可观测 StateGraph 阶段轴：记录 intake / plan / inspect / implement / verify / repair / summarize 节点、trace、运行统计和可序列化任务指标。真正的任务执行仍是 `run_agent` 工具循环；StateGraph 不是完整 workflow 引擎。
- 只读 DAG 可实际调度：inspect→summarize 等只读计划会执行；含写入的 DAG 模板只作为提示，由主循环落地。
- 验证器驱动闭环：成功写入后自动运行白名单 pytest，失败最多按 `MINICC_MAX_REPAIR_ATTEMPTS` 回到 repair；验证结果、失败测试、建议和耗时都会写入任务快照。
- 证据驱动完成评估：验证器之后由独立 LLM completion judge 根据原始需求、工具 trace、修改证据和验证结果返回结构化 `complete` / `continue` / `blocked`；`continue` 会把缺失目标反馈给 Agent 继续执行，评估失败会先触发一次复查，不会直接标绿。
- 自动并行编排：运行时按需求复杂度和独立工作维度评分；达到阈值后自动创建 2-3 个只读侦察子任务，独立 session 并行执行，父 Agent 收集证据后继续原始实现与验证。任务中心仍保留显式批量入口作为高级控制面板。
- 推理强度支持 `low`、`mid`、`high`、`xhigh`、`max`；Web 设置可按任务切换，网关不支持时会逐级降档并在 trace 中记录原因。修改后会自动要求下一轮检查 diff 和验证。
- 受约束动态规划：复杂 Web 任务会先请求模型生成小型 JSON 计划，服务端校验节点数、依赖深度、并发宽度、重试次数和工具白名单；非法或不可用计划自动回退固定 DAG，并记录来源与原因。自动并行子任务仍使用确定性只读职责模板。
- 依赖感知修复、本地证据检索和阶段路由：优先定位与失败测试和已写入路径相关的证据，并按 inspect/implement/verify/review 阶段选择合适的请求策略，不会覆盖用户显式配置的模型。
- 任务可靠性基线：SQLite 历史、只读检查点 digest 校验、任务级联网授权、脱敏审计导出和离线 30 条评测 fixture。
- Web 体验：亮色/暗色主题持久化、阶段摘要与工具轮次折叠、长输出边界、仅在用户已接近底部时自动跟随，避免阅读历史时跳屏。
- 支持 `AGENTS.md`、`CLAUDE.md`、`MINICC.md` 或 `.minicc/instructions.md` 项目指导文件；内容只作为工作约定，不能覆盖系统指令和权限边界。
- 交互命令：`/help`、`/tools`、`/status`、`/view`、`/compact`、`/collapse`、`/expand [n]`、`/clear`、`/exit`。
- CLI 阅读位置：工具输出默认只显示人类可读摘要；`/expand [n]` 按需查看单条原始结果，`--verbose-tools` 可启动时展开。`--session-id interview-1` 会保存脱敏的阅读锚点和最近工具索引，`--resume` 恢复会话与显示偏好。

运行与数据策略：

```text
# Web 和 CLI 任务没有总执行时间、模型轮次或工具调用数量上限。
# 任务会持续到模型交付、用户取消或服务进程结束；断流会自动恢复。
MINICC_MAX_REPAIR_ATTEMPTS=2
# 单次 provider 调用超时（秒，默认 180，上限 3600）。慢网关上把这一项调大即可，Web 服务与任务 worker 同受生效。
MINICC_TIMEOUT=180
# 验收评审最多把“看起来已完成”的答案退回重跑几次；每次是一整轮 agent，属于成本上限（1..8 夹紧）。
MINICC_MAX_COMPLETION_CONTINUES=3
# 以下是数据保留/并发容量，不会截断正在运行的模型任务。
MINICC_TASK_HISTORY_LIMIT=24
MINICC_TASK_HISTORY_MAX_AGE_DAYS=30
MINICC_TASK_EVENT_LIMIT=768
MINICC_TASK_STREAM_LIMIT=16000
MINICC_TASK_USAGE_LIMIT=64
MINICC_TASK_COMPACTION_LIMIT=64
MINICC_TASK_QUEUE_LIMIT=32
# 日志：默认 WARNING 到 stderr；MINICC_LOG_FILE 另存一份 UTF-8 文件
MINICC_LOG_LEVEL=WARNING
```

## 日志与可观测性

minicc 只用一处日志通道：`minicc/logging_setup.py`。CLI/REPL 的正文输出走 `minicc/cli_io.cli_out()`
（包内唯一 `print()` 所在），日志一律走 stderr 或 `MINICC_LOG_FILE`，因此管道里的协议内容不会被日志打断。

```powershell
# 复现一次失败任务并留下可 grep 的现场
$env:MINICC_LOG_LEVEL="DEBUG"
$env:MINICC_LOG_FILE="D:\logs\minicc.log"
.\.venv\Scripts\minicc-web.exe --workspace D:\面试项目\minicc-codex --port 8765
```

事件名与任务快照、SSE 时间线使用同一套词表，方便直接对照：

- 模型侧：`provider_protocol`、`provider_retry`、`provider_stream_error`（由 provider 状态回调写入）。
- 执行侧：`run_started`、`tool_round_finished`、`budget_exceeded`、`stagnation_guard`、`run_finished`。
- 任务侧：`task_started`、`task_cancelled`、`task_crashed`、`task_finished`（thread 与 process 两种执行器共用同一事件漏斗）。
- 外围：`audit action=… path=… level=…`（编辑/命令审计，`info|notice|warning` 映射到 `DEBUG|INFO|WARNING`）、`hook_executed`、`mcp_spawn`。

凭据不会进日志。每个 handler 都过一遍脱敏过滤器：既按标签匹配 `api_key=`、`Authorization:`、`?token=` 等键名，
也按值形态匹配 `sk-…`、`ghp_…`、`Bearer …`、JWT、PEM 等；启动时还会注册已解析的 `MINICC_API_KEY` 与
`minicc-web` token，按精确子串掩码（≤3 字符的注册值忽略，否则会抹掉半行普通日志）。脱敏是幂等的：已经脱敏的
标记不会被二次包裹。

聚合用量与成本查 `/api/metrics`：它按任务快照逐条累加 `tokens_used` 与 `cost_usd`，未计价模型单独计入
`unpriced_tasks`（不会当作 0 成本混进总额）。这条规矩同样管到总额本身：**没有任何**任务被计价时
`cost_usd` 是 `null`（不是 `0.0`——「不知道」和「没花钱」是两件事）；**部分**被计价时 `cost_usd` 是已计价那部分
的小计（一个下界，不是账单），并且 `cost_is_partial: true` 明说它不完整。`priced_tasks` / `unpriced_tasks`
给出两侧行数。并行批任务的父任务快照已经把子任务的用量汇总进去，所以总额只累加
根任务，被汇总掉的子任务行数放在 `subtask_rows`（不是偷偷丢掉）。汇总发生在父任务的**每一条终态路径**上——
合并成功、子任务失败、合并器抛错、父任务被取消或崩溃、以及从 worker 进程镜像回来的重连收尾，都算；这份汇总幂等（记录带 `children_rolled_up`，重启后从任务索引恢复不会再加一次；汇总过的结果负载会由**主机字段**记录（不是负载里可以自带的东西——被计费的一方不该能声明自己已经算过），所以重连时既不会少记子树、也不会二次相加），所以同一个子树既不会少记也不会双计。另一条同向的口径：结果为空的
`tokens_used` 视为「没有上报」而不是「成本为零」，不会抹掉这次运行逐轮已经上报过的用量。不带 `?workspace=` 时统计范围是共享任务索引里的
**所有**工作区，此时 `workspace_path` 为 `null`、`scope` 为 `all_workspaces`；带上过滤时 `scope` 回显该路径。
`/api/audit` 支持 `?level=warning` 与 `?min_level=notice` 过滤，
未知级别返回 400 并列出可选值。失败响应带稳定 `code`（`forbidden`、`task_not_found`、`unauthorized`、
`invalid_request`、`internal_error`），客户端不必解析中文措辞。


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

安装到别的机器（wheel / sdist）：

`pip install -e .` 只适合开发机。要真正把 minicc 装到别的环境，构建 wheel —— 工作台前端与
VSCode 伴生扩展会在构建期被复制进包目录（`minicc/web_static`、`minicc/ide_static`），
所以安装后不再依赖仓库布局：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-dist.ps1 -Clean
# 产物：dist\minicc-<version>-py3-none-any.whl 与 dist\minicc-<version>.tar.gz
# 等价的单行构建：python -m pip wheel . -w dist（只出 wheel，不出 sdist）

python -m venv D:\envs\minicc-clean
D:\envs\minicc-clean\Scripts\python.exe -m pip install (Get-ChildItem dist\*.whl).FullName
D:\envs\minicc-clean\Scripts\minicc.exe --version
D:\envs\minicc-clean\Scripts\minicc-web.exe --workspace D:\some\project --port 8765
# 打开 http://127.0.0.1:8765/：页面与 bundle 由包内 minicc/web_static 提供

# 可选：VSCode 伴生扩展随包分发，先定位再自行打成 .vsix
D:\envs\minicc-clean\Scripts\python.exe -c "import minicc.static_assets as s; print(s.ide_root() / 'vscode')"
```

版本号只有一个来源：`minicc/__init__.py.__version__`。`pyproject.toml`（动态读取）、
`minicc --version`、MCP `clientInfo`、构建出的 wheel/sdist 文件名以及 `ide/vscode/package.json`
都必须与它一致，`tests/test_packaging.py` 会逐项比对。

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
    },
    "remote": {
      "url": "http://127.0.0.1:3000/mcp",
      "headers": { "Authorization": "Bearer <token>" },
      "read_only": false
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

当前工作区的本地 `.env` 已配置为阶跃星辰 OpenAI 兼容网关（`.env` 已被 git 忽略，不会提交 API key）：

```text
MINICC_BASE_URL=https://api.stepfun.com/v1
MINICC_MODEL=step-3.7-flash
```

启动 Web 工作台后，打开左下角设置，在“模型”下拉框中可查看当前网关返回的模型列表（例如 `step-5-preview`），也可以点击刷新。模型和“推理强度”都只影响之后新建的任务；每个任务会把自己的选择保存到快照，恢复或并行执行时不会丢失。模型列表获取失败时仍会保留配置中的默认模型。

推理强度可以通过环境变量或 Web 工作台顶部的“推理强度”按钮（也可在设置面板）调整：

```text
MINICC_REASONING_EFFORT=high
```

界面档位使用 `low|mid|high|xhigh|max|ultra`；其中中档会按兼容网关标准发送为 `reasoning_effort=medium`。如果某个模型不支持所选档位，Provider 会依次降档，最后关闭该扩展参数并继续请求。

### 配置文件层（`config.json`）

除了环境变量和当前目录的 `.env`，配置还可以写在两层 JSON 文件里：

```text
<workspace>/.minicc/config.json   # 项目层，只对这个工作区生效
~/.minicc/config.json             # 用户层，所有工作区共用
```

完整优先级：显式参数 > 环境变量 > `.env` > 项目层 > 用户层 > 内置默认值。键名写去掉 `MINICC_` 前缀的小写形式，也可以直接写完整的环境变量名：

```json
{"model": "step-3.7-flash", "timeout": 300, "sandbox_mode": "host"}
```

`MINICC_HOME`、`MINICC_LOG_LEVEL`、`MINICC_LOG_FILE`、`MINICC_WEB_TOKEN`、`MINICC_ALLOW_PRIVATE_FETCH`、`MINICC_ALLOW_PRIVATE_MCP` 只从环境变量或 `.env` 读取（它们决定去哪里读配置、或在使用它们的模块里直接读 `os.environ`），写进 `config.json` 不生效。

写进 `config.json` 却没有任何解析逻辑读取的键——拼错的、改过名的、已废弃的——现在会在启动时逐条报 WARNING，说明它正按默认值运行，并给出最接近的正确键名；`minicc --print-config` 也会把它们列在 `ignored_keys=` 之后。在这之前这类键完全静默，用户看到的是一份和自己的想法无关的配置。

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
当 judge 逐字重复上一轮的缺失项与下一步、**且**那一整轮没有产生任何新的工具调用或验证时，任务事件里会多出一条
`completion_verdict_repeated` 观测（`detail` 带第几轮、复读的要求原文、工具/验证计数、`action: "observe_only"`）：它把「评委
每复读一次就多烧一整轮 agent」这件事变成每条任务可查的事实。**它不改变停止时机**——停止仍只由
`max_completion_continues`（默认 3 次 continue）决定，因为「更早停」需要客观判据已满足而评委仍在复读这类可满足的见证，
那是收敛策略而非记账。
触顶时的报错也不再只转述评委的意见：它会**同时说明客观验证那侧的结论**——「本次任务没有运行客观验证（没有产生工作区
改动）」/「当前工作区没有可运行的客观检查，验证被跳过——请补一条可执行的验收条件」/「客观验证已通过，未收敛来自完成
评估的判断而非检查失败」。这三种结束方式过去印成同一句话，而只有中间那一种能靠补验收命令解决。

## 代码审核与后续路线图

2026-09-20 做了一次全量审核（11 个子系统并行深读 + 逐行复核 + 用项目自身函数复现），结论与后续实施计划：

- [docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md)：已确认缺陷清单（P0/P1/P2/P3，全部带 file:line 与复核命令）、安全模型评估、能力差距矩阵，以及一节「已核验为不是缺陷」的防误修清单。
- [docs/ROADMAP_TO_PRODUCT.md](docs/ROADMAP_TO_PRODUCT.md)：8 个里程碑 / 36 周的逐步实施计划，每条任务带目标文件、具体改法与验收标准。

其中最优先的三项：流式增量重叠合并会静默吞字符并污染 `write_file`/`bash` 参数（`minicc/llm/openai_provider.py:878`）、恢复诊断阶段死循环（`minicc/agent/loop.py:1264`）、agent 可写 `.minicc/allowlist.json` 自我提权（`minicc/allowlist.py:165`）。复核命令见 [docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md) 第十二节。

## 当前边界

这是本地 coding agent：SQLite 保存任务、租约和可检索历史，适合单机使用。线程模式随服务退出而中断；独立进程模式有定时心跳和原子租约，Web 重启会重连仍存活的 worker。失效任务按安全检查点规则恢复，不能恢复到模型调用内部的精确位置。写入后和工作区变化后仍须重新检查。只读、审查和受限验证计划可以进入白名单 DAG；写入计划由主 Agent 执行。MCP 支持 stdio 和受限 HTTP transport；Docker 需要本机可用。OAuth、云端协作、自动提交和多用户权限体系不在当前范围内。`bash` 的 host 模式使用本机子进程，运行不可信仓库应使用 Docker 隔离。

Web 默认关闭写入和联网。界面明确显示文件、命令、网络三项有效能力；plan 强制只读，acceptEdits 允许编辑而命令仍受限，yolo 显式放开任务能力。线程与进程共用同一请求契约。

## 优化、验证与评测

完整实施及验收记录见 [优化计划](docs/DEEP_OPTIMIZATION_PLAN.md) 与 [交付说明](docs/OPTIMIZATION_DELIVERY_2026-09-18.md)。检索在遍历时排除依赖与缓存目录，并增量复用索引；凭据类文件按**名字**排除（`.env*`、`secrets.json`、`credentials.toml`、`service-account*.json`、`*.pem`/`*.key` 这类数据文件；`credentials.rs`、`secrets_store.py` 这样的源码不在排除范围内），因为一条命中本身就是「叫 agent 去读它」的指针，等同于把凭据库端上桌；上下文按完整工具轮次压缩；完成评估必须引用真实证据，失败检查不能被跳过检查覆盖。

自动验证按变更选择关联测试和前端检查，不再因存在 tests 目录就默认全量 pytest。可在 `.minicc/verification.json` 配置规则；相同依赖 digest 下复用通过结果。未知范围如实显示缺少自动检查。

自动验证响应任务取消并终止测试进程；换命令、权限或依赖会使成功缓存失效，验证期间输入变化不能标为通过。扫描规模或输入无法完整确认时关闭结果复用。配置错误会以验证阻塞状态显示，测试收集和帮助命令不算有效验收。

```json
{"rules":[{"paths":["web/**"],"commands":["npm run check:web","npm run test:optimization"]},{"paths":["minicc/changes.py"],"commands":["python -m pytest tests/test_optimization_core.py -q"]}]}
```

前端定向验收：`npm run test:optimization`；真实 HTTP 产品链路：启动 fake-provider 本地服务后执行 `npm run test:web`。不需要为每次小改动反复执行全量回归。

HTTP 路由覆盖用一条命令复现：`python scripts/route_coverage.py --check`（把选定的两个测试跑在 coverage 下，再逐条问「这条路由的分支体有没有被请求进过」）。不要用「这条路由的比较行执行过没有」当覆盖率：`do_GET`/`do_POST` 是平铺的 `if path == ...: return` 链，任何一条落到 404 的请求都会把整条链的比较行点亮——实测只跑一条 `POST /api/nope` 就得到 14/14 = 100%，而真正进入分支体的是 0/14。模块行覆盖率是另一个数，单独报，不冒充前者。

文档里的交叉引用用 `python scripts/doc_pointers.py --check` 复现：把 `docs/*.md` 与 README 里每条 `见/参见` 指针和每个相对链接真去解析一次——批号/节号必须落在一个**存在的标题**上，指针里同时点名编号时（`见「第十八批 M8-T34」`）该编号必须在**那一节的标题或表格行标签**里被声明过，只在正文里出现过不算数（指针自己就写着那个编号）。中文里「见」是常见后缀（可见、意见、见证），所以只抽带定位符或编号的片段。节号与批号**两种写法都认**：`第四节` 与 `第8节` 都是定位符，标题侧 `## 四、` 与 `## 8.` 都能答它——只教其中一侧，读得懂「第8节」却没有标题能答它，两条真断言会立刻变成两条假红。指针还**必须把文件名写进句子里**：昵称不是可查路径，`见交付说明第8节` 该红，写成链接形式才可核对。**每个标记必须落进八箱之一并在总结行逐箱报数**（当前定稿读数：`checked 50 of 166`，八箱 `checked=50`、`citation-without-locator=15`、`carried-by-link-reader=9`、`carried-by-evidence-reader=2`、`code-span-names-a-file=6`、`cites-a-quoted-name=1`、`path-in-prose=3`、`word-interior=80`），分箱之和还要与独立重数对账，不等报 `RECONCILE`——因为「其余计入一个整数」这种交代方式盖过一件事：`可见价值低于 M6–M8 任何一项` 曾被抽成指针并**绿着通过**（M6、M8 确实都在这个文件里），假指针比缺口糟，因为它往已核验那一栏记了一笔。定稿规则：span 里带节号/批号/附录号的一律算引用；只带编号的必须站在引用位置上（以引用词、`「`、`[`、编号本身开头）；span 为空时看未掩码的原文里紧跟的是代码片段还是链接——那两条分别归证据阅读器与链接阅读器，不算缺口；但「链接」那一半自 M8-T42 起要多问一句：对方究竟会不会判它。**托管要验一次发票**：那句「归证据阅读器」只在片段真的是对方会解析的形状时才成立；上一批这一箱记着 7 条，逐条问对方认不认，只有 2 条是真交接，剩下 5 条是裸文件名和被忽略目录下的路径——证据阅读器故意不判它们（否则正文里几十处 `loop.py` 简写会一夜变红），于是它们一直躺在「别人会查」那一栏。现在它们进 `code-span-names-a-file`，由指针阅读器自己答：带目录的按链接阅读器同一套存在性问，裸名允许命中任意一个被跟踪同名文件，被 git 忽略的算生成产物，还带行号范围的不得超过被引文件行数；既不像文件也不是证据形状的片段（只写着字段名的那种）落 `citation-without-locator`，不许落进词内箱——那一箱的含义是「根本不是引用」。**另一个交接箱同一条尺子**：`carried-by-link-reader` 过去只问「句子里有没有方括号」，可链接阅读器认的是完整的 `[文字](目标)`，而且目标还得是它愿意判的那类——空目标、页内锚点、外链、被空格打断的形状，它一概跳过。五个形状逐条量过：被记成已托管的那几条，链接阅读器实报 `checked=0`，一台说「这不是我的事」、另一台说「这不值得查」。现在判据换成对方自己的语法，且**两侧跳过表是同一份代码**（`_link_judged`，链接阅读器自己走它，指针侧问的也是它，改一处两边同变），反向一并修好：`见下方 [说明](README.md) 一条` 这种「方括号不在 span 首位」的真链接，过去被记成没有判据、其实一秒可核。`citation-without-locator` 之外还有一格 `cites-a-quoted-name`：`见下文「X」` 这种**用引号给一段起名字**的指针，过去抽取器根本不认（它的方位词表比判据表少七个词），本批认了、并给它一个阅读者——名字必须在指针声称的那一侧被**声明**在标题、粗体标签或表格行首格里，正文里出现过不算（M8-T36 的同一口径），包裹指针自身的那条标签也不算（否则指针就是在给自己的句子背书）。它刻意不进 `checked` 那个整数，那个整数继续只表示「定位符形状的目标被解析掉了」。只有 `见<方位词>「X」` 走这一格：裸 `见「X」` 引的是一段**描述**不是**处所**，仍由原来的 head 判据决定，否则「把链接形状写进反引号当例子」那条口径就失去受力点。剩下的 `citation-without-locator` 箱（`口径见下方注记`、`见上表末格`、`见本批末尾`）是**有名字、有条数、没有判据**的一格：16 条逐类量过之后确认「注记/表格某一格/相对位置/占位符 `第N批`」这几种落点都没有可核对的声明位置，任何「存在即通过」的判据都是自我满足，所以不假装它已解决。链接阅读器也先掩码：**把链接形状写进反引号当例子不是断言**（这条是记录自己撞出来的——撤掉掩码，语料里 5 个被引用的形状会全被当成断言）；代价与指针侧同一条口径：只在代码片段里出现的坏链接这里也看不见。

同一把量具还读**证据指针**：行内代码里的路径、路径:行号、路径.ext.属性、测试文件.py::测试函数名、裸 test_ 函数名，都是一条可解析的断言（这几类拼法故意写在正文里而不是代码片段里，因为读者把代码片段当断言——写它们的那一段自己就会被自己校验），全仓 19 个文档共 813 条断言，逐条真去解析——文件必须存在、行号不能超过文件行数、`::` 后的测试必须真的定义在那个文件里、属性名必须出现在被引文件里。**哪些名字算"仓库里的路径"从 git 索引推出，不从列目录推出**：同一份 HEAD 在开发机上曾经是 811 条，在干净检出是 782 条，差的 29 条全部落在 `.minicc/`、`output/`、`.venv/` 这类只在跑过东西的机器上存在的目录里；现在判据只看 `git ls-files`，所以这个数是 HEAD 的函数，与在哪台机器上跑无关（总结行会把基数一起打印出来，当前 228 个被跟踪文件）。链接判定同样是三态而不是"存在/不存在"：被跟踪→绿，被 `.gitignore` 忽略→计为生成产物（照计数、照打印、不报红，判据由 `git check-ignore` 现场回答而不是有人手抄理由），**本机有但 git 没跟踪→红**（这种断链只有作者看得见，所以必须留在红里）。豁免不是「这条不管了」，而是「这条的语义已经变了」，所以每条豁免必须带非空理由、必须仍被某个文档引用（否则算陈旧登记）、而且**必须真的答上过至少一条引用**（否则算死行：豁免键有两种角色，删掉会变红的"挡红型"和删掉只会让清单缩水的"准入型"，只按会不会红量活性就漏掉后者），目前共六类 14 个键：不是仓库路径、构建产物、计划里承诺但未交付、被引用来说明它已过期、主动退役、计划里否掉的拼法。当一个名字已经改名而记录必须留住它时，把死名字写在正文里、把活指针放在行内代码里：读者只校验代码片段，正文只校验带斜杠的路径，于是历史留住了、悬空指针也没有。明确没管的：围栏代码块内部、代码片段内部、快照与范围外文档里的悬空指针；无扩展名的模块名和裸文件名不算断言（`127.0.0.0/8`、`tools/call`、`loop.py` 都会被误判）；仓库外的路径形状串仍按存在性判；`--check` 尚未接入 CI，"干净检出 vs 开发机"这一组差异目前靠手动 `git worktree add` 复现。

新增 12 条隔离行为任务，验收器保留在任务工作区之外，覆盖边界值、异常和输入不变性。报告分别给出完成率、评分覆盖率、验收成功率、错误完成率、延迟及已知 token，用 fake provider 的结果只验证工程链路。

```powershell
# 仅生成报告，不调用模型
python -m minicc.benchmarks --suite behavior
# 使用当前配置的真实模型执行两条任务，可从已完成结果续跑
python -m minicc.benchmarks --suite behavior --run --max-tasks 2 --task-timeout 360 --results output/behavior-results.json
```
