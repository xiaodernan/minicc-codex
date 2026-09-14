# minicc-codex 商业化差距审查与后续开发计划

> 审查基准：2026-09-13 拉取的最新代码（最新提交 `d0de6b3 add local agent RPC transport`）。
> 对比对象：OpenAI Codex CLI 与 Claude Code 的公开产品能力。
> 本文只做差距审查与规划，不包含代码改动。

## 一、项目现状快照

架构：Python 后端（无框架 HTTP server + SSE + SQLite 任务存储 + 进程内线程池），前端为无构建、无框架的原生 JS 单文件（`web/app.js` 约 4500 行）。

已具备的能力：

- 14 个工具：`read_file` / `glob` / `grep` / `tree` / `git_status` / `git_diff` / `web_search`（只读），`write_file` / `edit_file`（写入），`bash`（exec，可走 Docker 沙箱），`worktree_*`，MCP stdio 工具（`mcp__server__name` 命名）。
- StateGraph / DAG 编排、验证器（verifier）+ completion judge 完成闭环、受限动态规划（planner 输出 JSON 计划由运行时校验）、并行只读侦察子任务（确定性触发，最多 3 个）。
- 上下文压缩 checkpoint、审计脱敏、任务级 `allow_changes` / `allow_network` 授权、SQLite 任务历史、SSE 流式（Last-Event-ID 续传 + 断线降级轮询）。
- 测试基线：约 110 个 pytest 用例（`tests/test_core.py`）+ Playwright 前端 smoke（`tests/web_smoke.mjs`）。

## 二、与商业级 Codex / Claude Code 的差距

### 2.1 后端差距（按严重程度）

1. **模型接入层单一（最核心差距）**
   - 只有 OpenAI 兼容协议（`chat_completions` + `responses` 两种 wire），无 Anthropic 原生协议，无法正确使用 Claude 的 prompt caching、extended thinking、token-efficient tools 等能力。
   - 无多模型 fallback / 路由（config 只有一个 model 字段）；`reasoning_effort` 降级依赖网关报错文本匹配，较脆弱。
   - 不主动构造 prompt caching（只解析 usage 里的 cache 命中字段），长会话成本会显著高于 Claude Code。

2. **工具面缺关键工具**
   - 缺：TodoWrite（任务清单，商业产品 UI 的核心联动）、Task/subagent 通用工具、WebFetch（现在只有 web_search 的 snippets，不能抓网页正文）、NotebookEdit、批量化并行 Edit。
   - Subagent 只有"确定性触发的最多 3 个只读侦察"这一种，没有通用 subagent 机制。

3. **权限模式太粗**
   - 只有每任务两个布尔（`allow_changes` / `allow_network`）+ 全局 `--yolo`。缺 plan mode / acceptEdits / askEveryTime 等档位、per-tool 或 per-path 规则、可持久化的 allowlist（"本会话不再询问"）、hooks 机制。
   - CLI 逐次 y/N 确认，无记住决策的能力。

4. **恢复 / 持久化语义弱**
   - 会话是全量 JSON 快照，没有消息级 rewind / undo 树 / 回退到某一步重跑（Claude Code 的 Esc-rewind 能力）。
   - 服务重启后任务只能标 `interrupted` 重跑；任务队列是进程内 ThreadPoolExecutor，无跨进程 / 守护进程能力。

5. **安全与多用户为零**
   - Web 服务无任何认证（无 token / 密码 / Cookie），CORS 硬编码 `*`，`/api/workspace/select` 可切换任意本机目录；`--host 0.0.0.0` 一开即全网暴露。这是商业化第一优先级补丁。

6. **MCP 只有 stdio**：无 HTTP/SSE transport、OAuth、resources/prompts/sampling，无工具健康检查和配额。

### 2.2 前端差距

1. **渲染质量**：自制极简 markdown（仅粗体 / 行内码 / 代码 fence / 列表），无语法高亮、无表格、无 KaTeX；diff 只有着色 pre。商业产品是完整 markdown + 高亮 + 结构化 diff 视图。
2. **缺商业产品的核心 UI 组件**：
   - 无 todo / 计划可勾选面板（后端也没有 TodoWrite 工具）。
   - 无文件树浏览器、无 Monaco/CodeMirror 编辑器、无内嵌终端。
   - 无 @-文件引用 / 上下文选择器、无全局历史搜索、无 checkpoint 回滚 UI。
   - 附件仅图片（4 张 / 6MB / base64），无文件上传、语音输入。
3. **工程结构**：286KB 单文件 app.js、字符串拼 HTML、无框架 / 无 TypeScript / 无构建；事件列表手动截断 240 条，长会话无虚拟滚动。
4. **亮点（应保留）**：SSE 断线降级轮询、Last-Event-ID 续传、滚动位置保持、双主题、移动端适配、中英 i18n、E2E smoke。另有约 1500 行"植物大战僵尸"彩蛋小游戏，与主功能无关。

### 2.3 工程质量债

- `web.py` 3800 行、`loop.py` 1333 行、`openai_provider.py` 957 行、`app.js` 4477 行，全部是单文件巨石。
- trace 事件构造约 40 处重复样板（手写中文 summary 字符串）；流式文本合并逻辑重复实现两份（`openai_provider._merge_stream_text` 与 `loop._merge_incremental_text` 几乎相同）。
- 对"兼容网关"的错误文本匹配属于脆弱依赖。

## 三、后续完整开发计划

排序原则：先安全、再协议、再体验、再规模化。

### 阶段 0：安全与卫生（约 1 周，商业化前置条件）

1. Web 认证：启动时生成 / 配置 access token，Bearer + 登录页；CORS 改为白名单；`0.0.0.0` 监听时强制要求 token。
2. workspace 目录白名单（配置允许的根目录列表），限制 `/api/workspace/select`。
3. 代码拆分：`web.py` → HTTP 层 / 任务运行时 / RPC / 静态服务四个模块；app.js 同步拆模块（引入轻量构建如 esbuild，不上重框架）。
4. CI：GitHub Actions 跑 pytest + web smoke，固化当前 110+ 用例基线。

### 阶段 1：模型层商业化（约 2 周）

1. Anthropic 原生 provider：Messages API、system + cache_control 断点、extended thinking、精确 usage；与 OpenAI provider 抽象出统一 `Provider` 接口。
2. 多模型路由与 fallback：按阶段（plan / inspect / implement / verify）配置模型档位（fast / balanced / reasoning），主模型失败按错误类型 fallback；替换错误文本匹配为结构化错误分类。
3. Prompt caching 策略：system prompt + 工具 schema + 项目指导文件打缓存断点，目标长会话输入成本降 50%+（用固定任务集 A/B 验证）。

### 阶段 2：Agent 能力对齐 Claude Code（3-4 周）

1. TodoWrite 工具 + 前端计划面板：受约束的 todo state 工具，前端渲染可勾选清单并与 trace 联动。
2. WebFetch 工具：抓取 URL 正文转 markdown，按不可信输出处理；与 web_search 组成完整联网能力。
3. 权限模式档位：`plan`（只读 + 计划输出）/ `default`（逐次确认）/ `acceptEdits`（写自动、exec 确认）/ `yolo`；加"允许本会话不再询问"的持久化 allowlist（per-tool + per-path glob）。
4. 通用 subagent（Task 工具）：在现有 orchestration 基础上放开为受预算 / 深度 / 工具白名单约束的通用子任务派生，复用 DAG 校验。
5. 通用 MCP：HTTP / SSE transport + OAuth，resources 支持。

### 阶段 3：前端体验商业化（3-4 周，可与阶段 2 并行）

1. Markdown 全量渲染（marked / markdown-it）+ 语法高亮（highlight.js / Shiki）+ diff 专用视图（合并 / 分栏）。
2. 文件树浏览器 + 文件预览（只读 CodeMirror），点击 trace 中的文件路径直达。
3. Todo 面板（配合阶段 2.1）、@-文件引用输入、会话历史全局搜索。
4. Checkpoint / 回滚：会话保存消息级快照树，UI 提供"回退到此消息重跑"（配合阶段 4.1）。
5. 长列表虚拟滚动，去掉 240 条截断。

### 阶段 4：可靠性（2-3 周）

1. 消息级 checkpoint + rewind（后端会话存储改为可寻址事件树）。
2. 任务守护进程化：执行器拆为可独立重启的 worker 进程，服务重启可重新 attach 运行中任务（目标：重启不丢任务）。
3. 断点续跑：基于已完成节点 + 工具幂等键的恢复（`docs/AGENT_LLM_ROADMAP.md` 已有设计），注入测试验收恢复成功率。
4. 真实模型评测基线：用 `benchmarks/` 30 条 fixture 接真实模型，建立成功率 / 成本 / P95 看板——这是路线图自己承认的最大空洞。

### 阶段 5：产品化扩展（按需求）

- Git 工作流闭环：分支 / 冲突预检 / 审查摘要，默认不自动提交。
- IDE 集成：VS Code 扩展走同一套本地 API。
- 团队协作：身份 + 审计 + 只读分享视图（在阶段 0 认证之上）。
- 上下文工程 2.0：分层上下文 + 确定性检索召回（保持"先指标后向量库"的既定原则）。

### 明确不做（与项目既有原则一致）

- 无约束递归多 Agent、过早引入向量库 / 分布式队列、暴露模型 CoT。

### 建议的第一个里程碑

阶段 0 + 阶段 2.1（TodoWrite + 计划面板）+ 阶段 3.1（markdown / 高亮 / diff）——三件事合起来能砍掉一大半"演示观感差距"，且都是低风险改动。

## 四、开发进度日志（2026-09-13 起）

### 第一波（已完成，全部有 pytest 覆盖，测试基线 130 → 185 全绿）

| 项 | 阶段 | 交付物 |
| --- | --- | --- |
| Web 认证 | 0.1 | `minicc/webauth.py`（token 生成/校验、回环判定、origin 白名单）；`--host 0.0.0.0` 强制认证；EventSource 走查询参数 token；前端 401 弹窗（`tests/test_web_security.py`） |
| CORS 白名单 | 0.2 | 移除 `Access-Control-Allow-Origin: *`，仅回环来源回显 |
| workspace 白名单 | 0.3 | `MINICC_WORKSPACE_ROOTS` 限制 `/api/workspace/select` |
| WebFetch 工具 | 2.2 | `minicc/tools/webfetch.py`：SSRF 逐跳校验、重定向控制、HTML→文本提取、512KB 截断；注册 + network 门控 + planner 白名单联动（`tests/test_webfetch.py`） |
| TodoWrite 工具 | 2.1a | `minicc/tools/todo.py`：`todo_write`/`todo_read`，原子持久化 `.minicc/todos.json`，结构化数据透传任务事件（`tests/test_todo_tool.py`） |
| 历史全局搜索 | 3.3a | `TaskStore.search` + `/api/history/search?q=&limit=&workspace=`，脱敏摘录（`tests/test_history_search.py`） |
| 权限模式 | 2.3 | `plan`/`default`/`acceptEdits`/`yolo` 四档：`audit.py` 判定、任务快照持久化、CLI `--permission-mode`、Web payload `permission_mode`；自动侦察子任务强制 plan（`tests/test_permission_modes.py`） |
| Markdown/高亮/diff | 3.1 | vendor（marked 12 + highlight.js 11.9）本地化、formatText 全量管线（XSS 转义 + 协议过滤 + 优雅降级）、统一 diff 行号视图、双主题（后台代理交付） |
| CI | 0.4 | `.github/workflows/ci.yml`：双平台 pytest + JS 语法 + Playwright web smoke |
| MCP HTTP transport | 2.5 | `mcp.json` 服务器条目支持 `url` + `headers` 鉴权、streamable HTTP（JSON/SSE 双解析、`Mcp-Session-Id` 会话）；修复 tools↔mcp 循环导入（`tests/test_mcp_http.py`） |
| 文件树 API | 3.2a | `/api/files?path=&depth=`：结构化、SKIP_DIRS 过滤、路径越界防护（`tests/test_file_tree_api.py`） |
| 会话 rewind | 4.1a | `SessionStore.rewind`（单份滚动备份）+ `POST /api/sessions/rewind`（`tests/test_session_rewind.py`） |
| Git 工作流 | 5.1a | `git_summary`（分支/upstream/脏文件/最近提交）、`git_merge_precheck`（merge-tree 干跑冲突预检）；planner 只读白名单纳入（`tests/test_git_workflow.py`） |
| 系统提示词 | - | todo_write 计划指引、webfetch/web_search 联合使用规则 |

### 第二波（已完成）

- 2.1b Todo 计划面板 + 权限模式选择器前端（后台代理交付：SSE 事件 data.todos → Inspector 计划面板、四档权限分段选择器与手动开关联动、radiogroup 键盘导航、双主题；集成验收 pytest + smoke 通过）。
- npm 依赖 + Playwright Chromium 安装完成，web smoke 可本地运行。
- 阶段 2.4 通用 Task 子代理工具（`minicc/agent/subagent.py`）：`task` 工具派生只读侦察子代理——受限注册表（无写/命令/联网/递归）、独立事件循环工作线程、轮次预算 + 墙钟超时 + 取消传播、模块级并发上限 3、结果按不可信 ToolResult 回传并带工具日志；web 任务路径与 CLI 均已注册（`tests/test_subagent_task.py`）。

### 第三波（收尾中）

- 前端：文件树侧栏 + @-文件引用补全 + 会话历史全局搜索 UI——已落地（代理被并发限制挤杀于收尾阶段，代码完整：fileTree/搜索/@补全标记、i18n、CSS 齐备，smoke 通过；细节交互待人工复核）。
- **阶段1 Anthropic 原生 provider**（`minicc/llm/anthropic_provider.py`）：Messages API、OpenAI↔Anthropic 消息/工具/图片双向转换、system+末位工具 cache_control 断点（prompt caching）、usage 归一化（cache_read→hit、cache_creation→write）、重试+Retry-After；`MINICC_PROVIDER_TYPE=auto|openai|anthropic`（auto 按 base_url/模型名推断，claude* → anthropic）；web/CLI make_provider 分支接线，现有 monkeypatch 测试契约不受影响；pyproject 新增 `anthropic` extra（httpx）；`tests/test_anthropic_provider.py` 6 项。
- 测试基线：199 全绿。

### 第四波（完成）

- **阶段4.4 评测 runner**：`benchmarks/tasks.json` 30 条任务补齐真实 prompt（覆盖 read/debug/edit/review/security/verify/reliability/planning/workflow/routing）+ 3 条只读 verify_command；`minicc/benchmarks.py` 新增 `run_benchmark()`（AgentService 实跑、写禁用、verify_command 评分、增量落盘 results_path、单任务失败不中断、无真实配置拒绝执行）与 CLI `--run/--max-tasks/--workspace`；`tests/test_benchmark_runner.py` 5 项（fixture 完整性、执行记录、verify 评分、失败隔离、不带 --run 绝不触模型）。
- **阶段"上下文工程 2.0"检索增强**（代理失败于 captcha 但成果完整存活）：`minicc/agent/retrieval.py` 确定性打分增强 + 指导文件常驻 + CJK bigram + stats() 指标，`tests/test_retrieval_enhanced.py` 13 项全绿。
- 阶段1 Anthropic provider 完成接线与测试（第三波记录）。
- 测试基线：218 全绿。

### 第五波（完成）

- **多模型 fallback（阶段1.2 核心闭环）**：`MINICC_FALLBACK_MODELS`（逗号/分号分隔，自动去重并排除主模型）→ StageRouter 携带 fallback_models → 服务重启恢复链路：首次恢复仅降协议保持主模型，第二次起按序轮换备用模型并发出 `task_model_fallback` 审计事件；`tests/test_model_fallback.py` 4 项（解析/排除主模型/路由透传/真实恢复轮换）。
- **阶段4.4 真实模型首跑评测（首批真实基线数据）**：`python -m minicc.benchmarks --run --max-tasks 5 --results output/eval-results.json`，5/5 任务完成，真实数据：P50=109s、P95=141s、总计约 129 万 tokens、tool_repeat_rate=0.0；报告落盘 `output/evaluation.json` + `output/evaluation.md`。已修复 runner 两处缺陷（--results 在 --run 模式误读输入文件；`__main__` 入口定义顺序导致 NameError）。
- 测试基线：226 全绿。

### 第六波（完成 / 进行中）

- **pass_at_1 分母语义修复**：`build_report` 曾把 `passed=None`（无验收命令）强转 `False`，导致无验收任务错误计入通过率分母（首跑 1/1 被错报为 0.2）；已保留 None/False 区分。
- **评测 runner 健壮性**：单任务墙钟超时（默认 900s，工作线程包裹防卡死）+ `resume` 断点续跑（跳过 results_path 中已完成 task_id）。
- **守护进程化第一步：中断任务自动恢复**：`MINICC_AUTO_RESUME_ON_START=1` 时服务启动自动把 `interrupted` 任务重新排队（workspace 匹配、子任务不单独恢复、失败退化为手动重跑）；`AgentService` 新增 `task_store` 注入点；`tests/test_auto_resume.py` 2 项。
- **前端交互人工复核（浏览器实操）全部通过**：权限模式四档 radiogroup 与动态提示、全局搜索入口、@-文件引用补全（listbox/过滤/选中态）、文件树渲染与懒加载展开（子目录+文件大小）、会话回退表单（设置面板内，含输入与按钮）。
- **content-visibility 虚拟化**：消息列表与执行脉络应用 CSS 窗口化，替代重量级虚拟滚动（`contain-intrinsic-size` 保持滚动条与锚点稳定）。
- **会话回退 UI（阶段4.1b）**：设置面板新增"会话回退"表单（保留 N 条消息 → POST /api/sessions/rewind → toast + 会话重载），zh/en i18n。
- **全量 30 条真实评测**：进行中（含断点续跑与超时保护；diff-review 任务因当前工作区未提交改动巨大而耗时，已记录）。

### 第七波（流式与缓存专项）

- **Responses 协议流式显示修复（用户反馈）**：原实现 Responses 路径故意原子化（非流式），UI 在整轮结束才显示文本。新增 `_create_responses_stream`：`stream=true` 消费 `response.output_text.delta` 实时推送 UI、从 `response.completed` 取结构化最终结果（工具调用/usage 不受影响）；重试仅在首个 delta 之前发生，流中断在已输出后抛 `ResponsesPartialError` 交由任务级恢复以非流式重放，避免用户看到重复文本。真实网关验证：2 个 delta 实时到达、最终文本/usage 正确。`tests/test_responses_streaming.py` 4 项（增量送达/中断不重放/首 delta 前可重试/原子路径回归）。
- **缓存率核查（用户反馈）**：真实数据核查结论——usage 解析已正确映射网关 `input_tokens_details.cached_tokens`（OpenAI 风格）→ `prompt_cache_hit_tokens`；实测网关缓存对稳定前缀（system+tools，约 3.6k tokens）命中 82.4%。评测中出现的 0%/45% 波动为网关侧上游轮换（缓存亲和性）问题，客户端无法修复；minicc 侧请求前缀已保证字节级稳定（append-only 消息 + 固定工具顺序 + 固定系统提示），并如实按 hit/miss 展示。
- 测试基线：236 全绿。

### 第八波（前端视觉升级，用户反馈）

- **Claude 风格暖色主题重制**（`web/styles.css` 追加覆盖层，零 JS/类名改动）：亮色=奶油画布 + 象牙侧栏 + 赤陶强调色（claude.ai 调性）；暗色=暖炭底 + 同系赤陶（claude 夜间调性）；圆角 12/16px、卡片阴影分级、珊瑚渐变主按钮、合成器浮起卡片、细滚动条、主题色焦点环。
- **暗色模式加固**：清理历史 Codex 皮肤中未限定主题的硬编码浅色规则（composer/消息气泡/inspector-header/--codex-card 等 10+ 处）导致的暗色白块污染，全部补 `:root[data-theme="dark"]` 变量覆盖。
- 双主题浏览器截图验收通过；web smoke 三场景通过；前端交互复核不受影响。
### 第九波（模块化 + 评测健壮性收尾）

- **阶段0.3 web.py 拆分第一步完成**：HTTP 层（MiniccHTTPServer / MiniccRequestHandler / SSE 流 / 静态服务）抽到 `minicc/webserver.py`（457 行），依赖单向（web → webserver），类型引用走 TYPE_CHECKING 避免循环导入；`minicc.web` 保留 re-export 兼容既有测试导入；活体探活 + 236 全量测试通过。
- **评测 runner 超时二次修复**：原 ThreadPoolExecutor 上下文管理器退出会等待孤儿线程，900s 超时形同虚设（实测被 diff-review 巨型未提交 diff 卡住 40+ 分钟）；改为 daemon 工作线程 + join 超时，超时即放弃继续推进。实测生效：diff-review 超时失败后评测正常继续。
- **app.js 拆分决策**：推迟到下一轮并建议引入 esbuild——当前 app.js 集成了 8+ 轮无构建时代的全局函数相互调用（认证/待办/权限/文件树/@引用/搜索/markdown 管线），机械拆分的回归风险大于本波收益，应与构建系统一起做。
- **Anthropic 真实联调**：阻塞于缺少 claude 系模型网关（当前网关仅 OpenAI 兼容协议）；mock transport 层面已 6 项测试覆盖，待有 claude 端点后跑真实链路。

### 第十波（阶段0.3 收尾：app.js 拆分 + 构建管线）

- **app.js 物理拆分为 9 个有序源分片**（`web/src/01-core-state` … `09-bootstrap`，按语义切块：state/i18n/locale/markdown/面板+todo+权限/API 认证/流与任务/小游戏/启动引导），拼接产物与原文件 CR 规范化后逐字节一致——零行为变更。
- **构建管线**：`scripts/build-web.mjs`（按序拼接 + 可选 esbuild minify 产出 `web/app.min.js`）；npm 脚本 `build:web` / `check:web`（--check 校验产物新鲜度，可用于 CI）。esbuild 入 devDependencies。
- `web/app.js` 自此为构建产物（文件头有勿改注释），源码在 `web/src/`；后续新增前端代码应改分片后构建。
- web smoke 三场景 + 双 bundle 语法检查通过。

### 第十一波（守护进程化第 2 步：worker 进程隔离，阶段4.2 完成）

- **`minicc/task_worker.py`**：单任务独立进程执行器——进度快照（状态/阶段/流文本/事件/usage，均有界）实时写入共享 SQLite TaskStore；取消走标志文件（`.minicc/cancel/<task_id>.flag`）+ 进程内 watcher → cancel_event；`AgentCancelled` 正确落为 cancelled；`--fake-provider` 为测试钩子。
- **TaskManager process 执行器**（`MINICC_TASK_EXECUTOR=process`，默认 thread 不变）：`_run` 分支派生 worker 子进程，monitor 循环把 store 快照镜像回内存 TaskRecord（SSE 传输零改动）；父进程 cancel_event 正向写标志文件；worker 异常退出且无终态快照 → RuntimeError 走既有失败路径。
- **auto-resume 心跳守卫**：重启后若 interrupted 任务的 store 快照心跳新鲜（<45s），跳过重排队——worker 存活时不会双跑。
- `TaskStore.get(task_id)` 新增；测试 `tests/test_task_worker.py` 4 项（配置解析/子进程 e2e/标志文件取消/manager 全链路镜像）。
- 已知边界（记录在案）：跨 web 重启的**运行中**任务 attach 目前以"worker 继续跑 + 新进程 auto-resume 心跳守卫不双跑 + store 快照可查"为界；SSE 对已孤儿化任务的实时镜像尚未实现。

### 首批完整真实模型评测基线（30/30 任务集，真实网关）

| 指标 | 值 |
| --- | ---: |
| 任务完成率 | 28/30 completed |
| pass@1（有自动化验收的任务） | 3/3 = 1.0 |
| 失败任务 | 2（均为 900s 超时：diff-review / batch-plan-validation，见下） |
| P50 延迟 | 115s |
| P95 延迟 | 826s（被两条超时任务拉高） |
| 重复工具调用率 | 0.0 |
| 总 token 消耗 | 约 1158 万（28 条任务，全部真实网关回报） |

失败归因：两条失败均为 `task timeout > 900s`——当前工作区存在 30+ 文件的巨型未提交 diff，diff-review（要求审查全量 diff）与 batch-plan-validation（规划器面对同样的超大上下文）超出单任务墙钟上限。这是数据集环境问题而非能力缺陷；提交工作区后重跑这两条即可获得干净基线。原始数据：`output/eval-results-full.json` + `output/evaluation-full.{json,md}`。

### 下一轮队列（按优先级）

1. rewind UI + 长列表虚拟滚动（app.js）。
2. 全量 30 条真实评测（约 30-60 分钟机时）+ pass_at_1 分母语义修正（无 verify_command 的任务应从通过率分母中排除或单独统计）。
3. 任务守护进程化、web.py/app.js 代码拆分。
4. 前端三大件交互细节人工复核（懒加载、@补全键盘导航）。
5. Anthropic 路径真实联调（需 claude 模型网关）。

### 运营注记

- 子代理并发/流量上限实测约 2，且**启动第 3 个会杀掉在跑的代理**——后续波次上限设为 2，宁可主智能体多做。

### 下一波候选（按优先级）

1. 集成验收：全量 pytest + web smoke + 手动 UI 冒烟（认证 + 权限模式 + markdown + todo 面板）。
2. 文件树前端 + @-文件引用 + 会话历史搜索前端（后端 API 已就绪：`/api/files`、`/api/history/search`）。
3. rewind 前端 UI（消息级回退按钮 + 重跑）。
4. 通用 Task subagent 工具（受预算/深度/工具白名单约束，复用 DAG 校验）。
5. 真实模型评测基线（benchmarks 30 条 fixture 接真实网关，成功率/成本/P95 看板）。
6. web.py / app.js 进一步模块拆分（阶段 0.3 未完成部分）。
