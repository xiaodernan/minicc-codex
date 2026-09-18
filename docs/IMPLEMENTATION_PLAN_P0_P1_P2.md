# minicc-codex 改进实现计划（P0 / P1 / P2）

> 来源：对照 Claude Code / Codex 的本地 MVP 审查。
> 原则：先修会穿的权限与会当场扣分的空壳，再补齐 harness / UX，最后做产品化扩展。
> 验收：每项都有代码改动 + 测试或可手工演示的 UI 路径。明确不做无约束递归多 Agent、向量库、Redis、多用户 OAuth。

## 范围一览

| 优先级 | 项 | 目标 | 主要文件 |
| --- | --- | --- | --- |
| P0-1 | webfetch 门控 | 关联网时 webfetch 必须 denied | `agent/loop.py`, `audit.py` |
| P0-2 | worker 密钥 | 禁止 api_key 进入 argv | `web.py`, `task_worker.py` |
| P0-3 | 空按钮 | 接线或删除 Codex chrome | `index.html`, `web/src/main.js` |
| P0-4 | 空会话 | 去掉假 transcript / 假 12 turns | `index.html`, `web/src/core/state.js`, `web/src/chat/markdown.js` |
| P0-5 | action-chip | 快捷 prompt 与并行/附件/演示分绑 | `web/src/main.js` |
| P0-6 | 产品 smoke | 发消息 → live-task；游戏测试拆出默认套件 | `tests/web_smoke.mjs`, `package.json` |
| P1-1 | 写后验证 | 只有测试/验证命令能清 verification | `agent/loop.py` |
| P1-2 | Anthropic 流式 | `content_block_delta` 实时推 UI | `llm/anthropic_provider.py` |
| P1-3 | CLI 共用授权 | CLI 走 `authorize_tool` | `main.py` |
| P1-4 | 消息级 rewind | 点某条 user 消息回退 | `session.py`, 前端 |
| P1-5 | 拆模块 + 图诚实 | 抽出 TaskManager；图编排标明可观测性 | `task_manager.py`, `graph.py` |
| P1-6 | 游戏降权 | 主包拆出；入口改为彩蛋 | `web/src/game.js` → `web/game.js` |
| P1-7 | 前端模块 + 图标 | esbuild 入口打包；本地 SVG 图标 | `scripts/build-web.mjs`, `icons` |
| P1-8 | 默认安全模式 | `allowChanges` 默认 false | `web/src/core/state.js` |
| P2-1 | 会话 allowlist | 本会话记住路径/命令 | `allowlist.py`, `audit.py` |
| P2-2 | 文件预览编辑器 | 高亮 + 行号的只读编辑器，trace 路径直达 | 前端 file preview |
| P2-3 | 软预算 | 可选 token/时长，先收束再停 | `config.py`, `loop.py` |
| P2-4 | MCP SSRF + sandbox auto | HTTP MCP 禁内网；默认 sandbox=auto | `mcp.py`, `config.py` |
| P2-5 | 文件级 rewind | 任务开始快照，可恢复工作区文件 | `snapshots.py` |
| P2-6 | VS Code 扩展 | 打开工作台 / 发送选区 | `ide/vscode/` |

---

## P0 安全与面试观感

### P0-1 webfetch 必须走授权

现状：`authorize_tool` 把 `webfetch` 当网络工具，但 `run_agent` 只对 `write`/`exec`/`web_search` 调用 `should_allow`。`webfetch` 风险是 `readonly`，直接执行。

实现：

- 在 `audit.py` 增加 `tool_requires_authorization(tool, risk)`：`write`/`exec` 或 `NETWORK_TOOL_NAMES`。
- `loop.py` 用该函数替代写死的 `web_search` 特例。
- 熔断逻辑对 `webfetch` 同样计数（连续失败停止空转）。

验收：`tests/test_permission_modes.py` 增加 loop 级用例——`allow_network=False` 时 webfetch 返回 denied，且不发 HTTP。

### P0-2 process worker 禁止 argv 泄露密钥

现状：`TaskManager._run_in_worker_process` 把整份 Config（含 `api_key`）塞进 `--config-json`。

实现：

- 配置写入 `workspace/.minicc/worker/<task_id>.config.json`，权限 0600。
- 命令行只传 `--config-file <path>`。
- worker 读完后删除该文件（测试可关）。
- 保留 `--config-json` 仅作测试钩子，Web 路径不再使用。

验收：`test_task_worker.py` 断言 Web 派生命令不含 `api_key`；子进程仍能完成 fake-provider 任务。

### P0-3 空按钮：接线或删除

| 控件 | 处理 |
| --- | --- |
| 文件/编辑/视图 | 删除（无对应功能） |
| 帮助 | 打开帮助面板（快捷键 + 彩蛋入口） |
| 后退/前进 | 删除 |
| 窗口三点 | 保留纯装饰，`tabindex="-1"` |
| 品牌 chevron | `openWorkspacesPanel()` |
| 品牌搜索 | `openGlobalSearchPanel()` |
| 通知铃 | 删除 |
| 侧栏「任务」 | 关闭面板回到当前会话，不再误开任务中心 |
| 装饰按钮 | 不可聚焦 |

### P0-4 空会话，不要假历史

- `index.html` 消息列表改为空状态（「发送一条任务开始」）。
- `state.turns` / `state.tools` 初始 0；`taskNavCount` 初始 0。
- `renderSession` 不再把 `interview-1` 的静态 HTML 当历史。
- Inspector「关注文件」初始行加上 `data-open-diff`，或等 `loadChanges` 后再渲染。
- 品牌名从 Codex 改为 minicc。

### P0-5 action-chip 分绑

只有带 `data-prompt-zh` 的芯片写入 textarea。`#batchButton` / `#attachButton` / `#demoFlowButton` 不再被通用 handler 清空输入。

### P0-6 产品路径 Playwright

- Web 服务支持 `MINICC_FAKE_PROVIDER=1`（与 worker 相同钩子）。
- `tests/web_smoke.mjs` 增加：填 prompt → 发送 → 出现 live-task / loading 消息。
- 断言：死按钮不存在或 `tabIndex=-1`；空会话没有假 pytest 时间线。
- `npm run test:web` 不再默认跑游戏套件；游戏保留 `npm run test:game`。

---

## P1 运行时与体验

### P1-1 写后验证不能被 git_status 满足

`VERIFY_TOOL_NAMES` 从 `{bash, git_diff, git_status, read_file, grep}` 收紧为：

- `bash` 且命令像验证：`pytest` / `unittest` / `npm test` / `ruff` / `mypy` / `tsc` / `node --check` / 白名单只读验证命令。
- `git_status` / `read_file` / `grep` **不算**验证。

验收：写文件后只跑 `git_status` 仍触发 `verification_required_before_finish`；跑 `python -m pytest -q` 后可以结束。

### P1-2 Anthropic 流式

- `stream=true` 消费 SSE：`content_block_delta.text_delta` 调 `on_delta`。
- 工具调用从 `content_block_start` + `input_json_delta` 聚合。
- 重试只发生在首个 delta 之前；已输出后中断不重放。
- 无 `on_delta` 时保持原子 JSON 路径。

验收：`tests/test_anthropic_provider.py` 用 MockTransport 推送 SSE 事件。

### P1-3 CLI 与 Web 共用 `authorize_tool`

`_permission_gate`：

1. 先 `authorize_tool`（plan / yolo / acceptEdits / 网络）。
2. 策略拒绝则直接 False。
3. 策略允许但仍需人工确认的 write/exec（default 模式）再 `input()`。
4. 增加 `--allow-network`。

### P1-4 消息级 rewind

- `SessionStore.rewind_to_user_index(n)`：保留到第 n 条 user 消息（含 system）。
- API：`POST /api/sessions/rewind` 增加 `user_index`。
- UI：每条 user 消息「回退到此」；设置里的「保留 N 条」保留为高级项。

### P1-5 拆 `web.py` / 诚实的图编排

- `TaskRecord` + `TaskManager` → `minicc/task_manager.py`；`web.py` re-export。
- `loop.py` 抽出 `tool_requires_authorization` / `is_verification_evidence`。
- `StateGraph` 文档与代码标明：**可观测阶段轴，不是执行器**。真正循环仍是 `run_agent`；只读 DAG 仍可执行。禁止在讲解/README 里把它写成完整 workflow 引擎。

### P1-6 游戏降权

- `08-game.js` 不再打进 `app.js`，产出独立 `web/game.js`。
- 主导航去掉「小游戏 NEW」。
- 入口：`?arcade=1` + 帮助面板彩蛋。

### P1-7 前端模块化 + 本地图标

- `web/src/main.js` 作为 esbuild 入口，`format: iife` 打出 `web/app.js`。
- 源码按职责拆：`core/`、`chat/`、`panels/`、`files/`（允许从现有分片迁移，必须有 `import`/`export`）。
- Lucide 不再假设全局；内联 SVG 图标表（本地、无 CDN）。
- `npm run check:web` 校验产物新鲜度。

### P1-8 默认安全模式

`allowChanges: localStorage.getItem("minicc-allow") === "true"`（缺省 false）。
文案与「受保护工作区」一致。yolo 模式仍可一键放开。

---

## P2 产品化扩展

### P2-1 会话 allowlist

`.minicc/allowlist.json`：

```json
{ "sessions": { "interview-1": { "commands": ["python -m pytest*"], "paths": ["web/**"], "tools": ["edit_file"] } } }
```

`authorize_tool` 命中则放行并审计 `session_allowlist`。
CLI 确认后可输入 `a` 写入本会话。
Web 设置面板可增删规则。

### P2-2 文件预览编辑器

- 预览改为行号 + highlight.js 高亮（已 vendor，不引入 Monaco 体积）。
- 工具时间线里的路径可点击打开同一预览。
- 只读；复制按钮。不做内嵌可写 IDE。

### P2-3 软预算

- `MINICC_SOFT_MAX_TOKENS` / `MINICC_SOFT_MAX_DURATION_SECONDS`（默认关闭，兼容「任务无硬上限」）。
- 超限：先插入收束提示再给模型一轮；仍超则停止，不抛成普通 BudgetExceeded 截断无摘要。

### P2-4 MCP HTTP SSRF + 默认 sandbox=auto

- MCP `url` 解析后拒绝 loopback/私网，除非 `MINICC_ALLOW_PRIVATE_MCP=1`。
- `DEFAULT_SANDBOX_MODE = "auto"`（无 Docker 时仍 host，有 Docker 则隔离）。

### P2-5 文件级 rewind

- 任务开始时把当时 git 脏文件 + 即将写入的备份纳入 `.minicc/snapshots/<task_id>/`。
- `POST /api/workspace/restore` 按快照恢复（不 `git reset --hard` 用户无关改动）。
- UI：任务详情「恢复此任务开始前的文件」。

### P2-6 VS Code 扩展（最小）

`ide/vscode/`：

- `minicc.openWorkbench` 打开本地 Web。
- `minicc.sendSelection` 把选区复制为可粘贴到工作台的 prompt 草稿。
- 不实现第二套 Agent 协议。

---

## 实施顺序

1. P0 后端（门控 + worker 文件）+ 测试
2. P0 前端（chrome / 空会话 / chip）+ 产品 smoke
3. P1 后端（验证 / Anthropic 流式 / CLI 授权 / 拆分）
4. P1 前端（游戏拆出 / 模块打包 / 默认安全 / 消息 rewind）
5. P2 全项
6. 全量 `pytest` + `npm run test:web` + `node --check`

## 落地状态

| 项 | 状态 | 验证 |
| --- | --- | --- |
| P0-1 webfetch 门控 | 已完成 | `tests/test_p0_p1_p2.py` |
| P0-2 worker 密钥 | 已完成 | `tests/test_p0_p1_p2.py` / `tests/test_task_worker.py` |
| P0-3 空按钮 | 已完成 | `tests/web_smoke.mjs` empty chrome |
| P0-4 空会话 | 已完成 | 同上 |
| P0-5 action-chip | 已完成 | `web/src/main.js` 仅 `data-prompt-*` 写入输入框 |
| P0-6 产品 smoke | 已完成 | `npm run test:web`（游戏不在默认套件） |
| P1-1 写后验证 | 已完成 | git_status 不能清 verification |
| P1-2 Anthropic 流式 | 已完成 | `tests/test_anthropic_provider.py` |
| P1-3 CLI 共用授权 | 已完成 | `--allow-network` + `authorize_tool` |
| P1-4 消息级 rewind | 已完成 | `tests/test_session_rewind.py` |
| P1-5 拆模块 + 图诚实 | 已完成 | `minicc/task_manager.py`；图为可观测阶段轴 |
| P1-6 游戏降权 | 已完成 | `web/game.js`；`?arcade=1` |
| P1-7 模块 + 图标 | 已完成 | esbuild IIFE + 本地 SVG |
| P1-8 默认安全模式 | 已完成 | `allowChanges` 缺省 false |
| P2-1 会话 allowlist | 已完成 | `tests/test_allowlist.py` |
| P2-2 文件预览 | 已完成 | 行号 + highlight.js，trace 路径可点 |
| P2-3 软预算 | 已完成 | wrap-up 后停止 |
| P2-4 MCP SSRF + sandbox auto | 已完成 | `tests/test_mcp_http.py`；默认 `auto` |
| P2-5 文件级 rewind | 已完成 | `tests/test_snapshots.py` |
| P2-6 VS Code 扩展 | 已完成 | `ide/vscode/` |

验收命令：`python -m pytest tests/ -q`；`npm run test:web`；`node --check web/app.js web/game.js ide/vscode/extension.js`。

## 非目标

- 无约束递归 subagent
- 向量 RAG / Redis / 分布式队列
- 暴露模型私有 CoT
- 自动 `git commit`
- 完整 Monaco / 内嵌终端
