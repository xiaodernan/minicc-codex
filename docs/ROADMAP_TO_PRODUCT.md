# minicc-codex → Claude Code / Codex 级：实施路线图

> 制定日期：2026-09-20。基线：当前工作区（`git log` 最新 `0366425`）。
> 配套文档：[AUDIT_2026-09-20.md](AUDIT_2026-09-20.md)（本路线图依据的全部已确认缺陷与证据）。
> 方法：4 个独立战略角度的候选路线图 → 3 个评委按 5 项标准打分（假设正确性 / 排序 / 工期现实性 / 达成目标 / 尊重非目标）→ 综合优胜方案并嫁接次优方案的最佳想法 → 完整性批判 → 主审核人逐行复核关键声明。
> 评分结果（均值 / 50）：可靠性优先 **41** > 能力对齐优先 39 > 评测驱动爬坡 31。
> 本文只做规划，不含代码改动。所有严重度与 file:line 以 AUDIT 文档为准。

## 一、结论先行

**现状：引擎已接近 Claude Code / Codex 的同级设计，产品外壳与可信度还差两级。** ReAct 循环、按完整工具轮次压缩、协议校验、变更驱动验证指纹、受约束 DAG、证据驱动完成判定，这些核心不变量都是真实设计而非摆设，388 个 pytest 全绿；双协议 provider 的重试边界、永久性 4xx 不重投、Retry-After 封顶、已交付文本不重投，比同规模项目更严谨。

**但有三类地基随时失效，且都在最关键的位置。** 一、会挂死：`loop.py:1263` 的恢复保护在纯文本回复时不自增任何计数器，而常规 Web/CLI 路径 `Budget` 全是 `None`（`web.py:730-733`），没有后备上限，这是唯一一个发起任务后必须人工杀进程的缺陷，且 `web.py:1450` 每次 repair/恢复后都可能触发。二、会静默损坏数据：`openai_provider.py:878` 把只该用于「重试 attempt 全文对齐」的重叠合并应用到了每一个增量 delta 上，`{"command":"echo hi` + `hi"}` 会变成内容错误的合法 JSON——这直接污染 write_file/bash 的参数；`:785` 把 `response.failed/incomplete` 原样透传为非 `stop` 的 `finish_reason`，但 `loop.py` 全文不校验 `finish_reason`，仍当成功答案交付。三、会泄密与自我提权：agent 写 `.minicc/allowlist.json` 即借 `allowlist.py:165` 的 `fnmatch(name,"*")` 拿到全部 bash 权限；`read_file('.minicc/web_token.json')` 原样返回 bearer；`workspace_roots` 只在 `web.py:383` 一处生效，任务提交与 RPC 入口可把 agent 指向任意目录。

**同时最刺眼的空洞是「不可证伪」**：pass@1 分母只有 3（30 条 fixture 里 27 条无 verify_command，且 0 条带 fixture 字段、allow_changes 全为 None，等于编码能力从未被度量）；CI 唯一端到端 web smoke 在 provider 指向不可达地址时仍打印 passed；`cost_per_success_usd` 恒 None。

**差距的真实分布**：不在引擎，在「能不能委派、能不能受控、能不能扩展、能不能记住、能不能便宜、能不能装上」。所以本路线图把 100% 的能力扩张压到第 12 周之后——在此之前，可写子代理会把「一条命令自我提权」复制成「每条并行分支都能提权」，hooks 会把 plan 模式可跑 bash 变成每次工具调用都能跑 bash，后台 shell 会把同步卡死变成后台无限累积。总工期 **36 周（兼职，约 8 个月）**，不是 21 周：21 周是把 7 个任务的 M1 估成 3.5 周那种系统性乐观约 30–40% 的结果。

---

## 二、里程碑总表

| id | 标题 | 周数 | 目标 | 退出标准 | 依赖 |
| --- | --- | --- | --- | --- | --- |
| M1 | 核心链路可信：provider / loop 的真相层 | 4.5 | 让「模型→工具→结果」这条管道会终止、不静默损坏数据 | 双平台 pytest 全绿且新增 ≥30 条完整性用例；`scripts/reliability_probe.py` 退出码 0 并接入 CI；假网关只发 delta + `[DONE]` 不发 finish_reason 时单轮只发 1 次 HTTP 请求且以明确错误结束；golden delta 逐字节往返相等 | 无 |
| M2 | 权限模型与工作区边界封闭 | 4 | 关闭 agent 自己授权自己、工作区边界可绕过、plan 模式 DAG 越权三条路 | `tests/test_security_perimeter.py` ≥12 条先红后绿；四个安全测试文件全绿；`docs/SECURITY_CHECKLIST.md` 记录四类人工攻击全部被拒 | M1 |
| M3 | 凭据、网络与进程面 | 4 | 收紧谁能驱动 agent、agent 能出网到什么程度，修掉编排层永久卡死与状态损坏 | Origin/CSRF 与网络门新用例全绿；非回环 Origin POST 403；强杀 worker 后 `.minicc/worker/` 无明文 key 残留且可 auto-resume；`grep -rn sk-` 在 `.minicc/` 与日志无命中 | M2 |
| M4 | 证据链与评测可信度（含价格表、A/B 门） | 5 | 先把「行不行」变成可度量、可复现、CI 能拦截的事实，再谈能力 | 四项证据链回归通过；不可达 provider 下 `npm run test:web` 退出码非 0；POST `/api/*` Python 测试覆盖率 100%；`--suite v2` 输出 grading_coverage=1.0、pass@1 分母 ≥24（edit ≥10）；A/B gate 违反 exit 1 且 CI 用构造数据验红；任务事件带 `cost_usd` | M1, M2 |
| M5 | MCP 桥加固与 CLI 接线 | 3 | 让零测试护网的默认传输层可信：输出有界、id 容错、reader 有监督、spawn 有门控 | `tests/test_mcp_stdio.py` ≥8 条；50 万字符输出截到 ≤6000；reader 死后后续调用 <1s 失败而非 30s；CLI `/tools` 列出 `mcp__` 工具 | M2 |
| M6 | 能力扩展 I：有界可写委派与后台执行 | 5 | 从只读侦察子代理到有界可写委派，补上后台 shell，写/exec 并行 | 跨 3 文件改造由 2 个可写子代理并行完成且 verifier 通过、父会话协议校验通过；超预算任务以 `BudgetExceeded` 结束；后台 shell 可轮询可取消且取消后无残留进程；30 条 fixture 重跑 token/task 与 P95 劣化 ≤15% | M4, M5 |
| M7 | 能力扩展 II：Hooks、slash 命令、交互审批、项目配置 | 4.5 | 从 agent 变成可扩展的 agent 平台，把 M2 的「拒绝」升级为「询问」 | hooks 四事件各一条集成测试（含超时与失败隔离）；自定义 slash 命令 CLI 与 Web 双端生效且不能覆盖权限边界；Web 一次真实审批从请求到落库；项目级配置覆盖生效且优先级文档化；断网提交后 composer 完整恢复 | M6 |
| M8 | 记忆、会话 fork、插件 API、可安装产物与可观测 | 6 | 从「能跑的仓库」变成「别人能装上、出问题能查、上次教它的事它记得」的产品 | fork 会话文件独立且 `--resume` 可恢复；跨 session 记忆索引可见且可手工编辑；`docs/PLUGIN_API.md` 示例原样跑通；干净 venv 装 wheel 后两个 entry point 均可用且 UI 200；DEBUG 日志含关键事件且不含 api_key；`print()` 下降 ≥80%；`test_core.py` 拆分且测试数不降 | M7 |

**总工期 36 周 ≈ 8 个月（兼职）。** 若排期滑出 9 个月上限，按此顺序砍：M8-T1 长期记忆 → M8-T2 会话 fork → M7-T2 Skills（保留 slash 命令）→ M6-T3 写/exec 并行。前四个里程碑一刀不砍。

---

## 三、里程碑详细任务清单

### M1 核心链路可信：provider / loop 的真相层（4.5 周，依赖：无）

**目标**：DAG、子代理、MCP、完成判定全部消费这条管道的输出——流式增量被按字符删减会直接污染 write_file/bash 的参数；失败的模型轮次被当成成功答案会让任务谎报完成；恢复保护死循环让任务永不返回。

**退出标准**：
1. `python -m pytest -q` 在 Windows + Ubuntu 全绿，新增 ≥30 条 provider/loop 完整性用例；
2. `scripts/reliability_probe.py` 一条命令复现本 milestone 全部缺陷，退出码 0，接入独立 CI job（失败即红）；
3. 人工核查：本地假网关只发 text delta 加 `[DONE]`、从不发 finish_reason，跑单轮任务确认只发 1 次 HTTP 请求且以明确错误结束（不是 5 次重放、不是空答案成功）；
4. golden delta 序列（空行、缩进、重复 token、tool 参数 JSON 分片）逐字节往返相等，streamed text 与最终 answer 一致。

**任务**：

- **M1-T1 修复恢复诊断阶段的无限循环（P0）** — `minicc/agent/loop.py:1258-1295`
  改什么：`loop.py:1263-1295` 的 plain-text 分支只读 `stagnation_replans` 却不自增它——该计数器仅在工具调用分支 `loop.py:1210` 自增；一旦进入纯文本分支就停在进入时的值不再变化。常规 Web/CLI 路径 `Budget` 全是 `None`（`web.py:730-733`，`state.py:58-60` 对 `None` 跳过），无总轮次上限。新增独立 `recovery_refusals` 计数器，在 `continue` 前自增，超过 `STAGNATION_REPLAN_LIMIT` 后 `break` 并写 `result.error` 加一条 `phase=failed` trace。
  验收：`tests/test_p0_p1_p2.py::test_recovery_required_does_not_loop_on_plain_text`——FakeProvider 恒定返回纯文本且 `require_recovery_inspection=True`，断言 `STAGNATION_REPLAN_LIMIT` 次后以 error 结束、总 turn ≤5，并用 `asyncio.wait_for(20)` 确保不挂死。

- **M1-T2 非流式 tool_call id 去重（P0）** — `minicc/llm/openai_provider.py:755-770`、`:965-985`
  改什么：`:975`（`_to_response`）与 `:761`（`_responses_to_response`）在网关省略 id 时给同一轮所有调用赋同一个 `call-0`（流式路径 `:942` 已正确用 `f"call-{index}"`）。改为 `enumerate` + `or f"call-{index}"` 兜底。
  验收：非流式响应含 3 个无 id 的 tool_calls 时得到 `call-0/call-1/call-2`；随后 `context.py:30` 的 `validate_tool_protocol` 不抛重复 ID 错误，3 个工具全部执行且结果回填。

- **M1-T3 流式增量重叠合并吞字符（HIGH）** — `minicc/llm/openai_provider.py:860-900`、`minicc/agent/loop.py:191-207`、新增 `minicc/llm/stream_merge.py`
  改什么：`openai_provider.py:877-880` 对每个 delta 调用 `_merge_stream_text`，把上一个 delta 尾部等于下一个 delta 头部的字符静默删掉；`loop.py:191-207` 的 `_merge_incremental_text` 是同一缺陷的第二份逐字拷贝。修法：同一次 attempt 内逐字节拼接，重叠去重只保留给重试 attempt 的完整文本对 `committed_text` 的合并（且仅对已知会重放 cumulative 快照的网关开启）；抽出 `minicc/llm/stream_merge.py` 作为唯一实现并删除 loop.py 拷贝。
  验收：新建 `tests/test_stream_merge.py`——序列 `["line one\n", "\nline two\n", "    indented\n"]` 必须逐字节拼回原串；tool 参数分片 `{"command":"echo hi` + `hi"}` 必须得到 `json.loads` 后 `command == "echo hi"`；`grep -rn _merge_incremental_text minicc/` 返回 0 命中；该测试在未修复代码上必须失败。

- **M1-T4 失败/截断的模型轮次不再伪装成成功（HIGH）** — `minicc/llm/openai_provider.py:770-800`、`minicc/llm/anthropic_provider.py:240-260`、`minicc/llm/base.py`、`minicc/agent/loop.py:1258-1300`、`minicc/config.py`
  改什么：`:785` 把 `response.failed` / `incomplete` 原样透传为非 `stop` 的 `finish_reason`，但 `loop.py` 全文不读 `finish_reason`（`grep` 只命中 docstring 第 10 行），纯文本分支无条件取 `response.text` 当最终答案接受，任务报完成、答案为空、`error=None`。`:252` 硬编码 `max_tokens: 8192`，无按模型钳制、无开关，Anthropic 截断按正常结束交付。改为 loop 的 text-only 分支显式拒绝非 `stop`/`tool_calls` 的 `finish_reason`（或抛新增的 `NonTerminalModelTurn`）；`max_tokens` 从 config 按模型钳制。
  验收：单测——`response.failed` 时 `run_agent` 以 error 结束而非空答案；`finish_reason=max_tokens` 截断时 error 或显式 continue；`stop_reason=refusal` 时任务 status != completed；`grep` 确认 8192 字面量已移除。

- **M1-T5 缺 finish_reason 的流不再整段重放（HIGH）** — `minicc/llm/openai_provider.py:895-915`、`_is_stream_retryable`
  改什么：`:900` 把流结束但无 finish_reason 判为可重试瞬态，默认 `max_retries=4` 即每轮 5 次完整重发上下文与工具 schema（`stop_after_attempt(self._max_retries + 1)`），此类网关上任务永久不可用。新增 `StreamProtocolError` 并从 `_is_stream_retryable` 排除。
  验收：`max_retries=2` 时断言只发 1 次 HTTP 请求、立即抛错、信息含 `stream ended before completion`；同时保留现有 `ResponsesPartialError` / `AnthropicPartialError 已交付文本不重投` 的测试不得回归。

- **M1-T6 Anthropic 缓存记账诚实化（MEDIUM）** — `minicc/llm/anthropic_provider.py`、`minicc/llm/usage.py:45-60`、`minicc/agent/state.py:71`
  改什么：`usage.py:51` 用 `prompt_tokens` 减 hit 推 miss，而 Anthropic 的 `input_tokens` 不含 cache token（input=100/read=80/write=12 被算成 miss=20、total=120），`state.py:71` 的 `record_usage` 按 `total_tokens` 记账使软/硬 token 预算被实质绕过。改为 provider 侧设 `prompt_tokens = input + cache_read + cache_write`、`prompt_cache_miss_tokens = input_tokens`，`usage.py` 的共享归一化保持不变。
  验收：用 `tests/test_anthropic_provider.py:75` 的 payload 断言 `miss=100`、`hit_rate=0.44`、`total=192`；并断言 `Budget(soft_max_tokens=...)` 在该 usage 下触发软预算；OpenAI 侧既有行为不变。

- **M1-T7 envelope 合成 id 复用与历史回放丢 tool_calls（MEDIUM）** — `minicc/llm/envelope.py:143-150`、`minicc/llm/openai_provider.py:1018-1030` 与 `:700-712`
  改什么：`envelope.py:145` 用 `id(obj)` 当合成 id，同一 session 所有 envelope 轮共用一个 id，`context.py:359-372` 解析到最新一轮，早期工具轮被 compaction 切掉后 `validate_tool_protocol` 抛协议无效，任务以 LLM 调用失败死掉。`:1027` 与 `:706` 在原生降级为 envelope 后（`:468` 粘滞）把历史 assistant tool_calls 折叠成空 content。改为 uuid4 或单调计数器；降级时渲染 `{"action": name, "params": json.loads(arguments)}`。
  验收：连续 3 轮 envelope id 互异；回放历史时 assistant content 包含 action 与 params；80 轮 envelope 会话触发压缩后 `run_agent` 不抛协议错误。

- **M1-T8 可靠性探针与 CI job** — 新增 `scripts/reliability_probe.py`、`.github/workflows/ci.yml`
  改什么：把 audit 的复现脚本固化为一条命令可复现的探针（覆盖 M1 全部缺陷），接入独立 CI job。
  验收：`python scripts/reliability_probe.py` 退出码 0；CI 中该 job 失败即红；audit 的一次性复现脚本全部删除或搬进 `tests/`。

### M2 权限模型与工作区边界封闭（4 周，依赖：M1）

**目标**：关闭 agent 自己给自己授权、工作区边界可被绕过、plan 模式 DAG 越权这三条最危险的路。在此之前，任何会写文件、会派生进程的能力（可写子代理、hooks、MCP、后台 shell）都是在给一个可提权的执行体加杠杆。

**退出标准**：
1. 新增 `tests/test_security_perimeter.py`，每个 finding 一条回归测试（≥12 条），**先红后绿**——在未修复代码上必须失败、修复后通过（防止写成恒绿断言）；
2. `python -m pytest -q tests/test_web_security.py tests/test_permission_modes.py tests/test_allowlist.py tests/test_file_tree_api.py` 全绿；
3. 人工攻击清单写进 `docs/SECURITY_CHECKLIST.md` 并全部被拒：`workspace_roots=(A,)` 时 `switch_workspace(B)`、`POST /api/tasks {workspace_path:B}`、`/api/rpc turn/start {workspace_path:B}`、`/api/chat` 四入口全部返回越界错误且不创建任务；plan 模式提交复杂度 ≥4 的调研任务不产生任何 bash 执行；A 内 junction 指向外部目录后 grep/glob/tree/file_tree 四条路径均不出现外部条目；acceptEdits 下 `write_file('.minicc/allowlist.json')` 被拒；`read_file('.minicc/web_token.json')` 不返回 token 原文。

**任务**：

- **M2-T1 workspace_roots 白名单单一入口（HIGH）** — `minicc/web.py:195`、`:377`、`:640`；`minicc/task_manager.py:1224`；`minicc/workspaces.py`
  改什么：grep 显示只在 `web.py:383` 的 `switch_workspace` 生效；任务提交与 RPC 完全绕过（`workspace_roots=(A,)` 时 `tasks.submit({"workspace_path": B})` 返回 running，带 bash/write_file 的 agent 可指向任意目录）。抽出唯一 `_resolve_workspace_path()`（含 `resolve` 与 `is_relative_to` 校验），四处统一调用。
  验收：`workspace_roots=(A,)` 时四入口全部返回越界错误且不产生任务记录；B 在 A 内部时全部放行。

- **M2-T2 封死 allowlist 自举提权与凭据文件可读（P1）** — `minicc/allowlist.py:165`、`minicc/audit.py:112`、`minicc/tools/editor.py:185`、`minicc/tools/fs.py:30`
  改什么：`allowlist.py:165` 对 `rules["tools"]` 做 `fnmatch(name, "*")`，`editor.py:185` 的 `_resolve` 只拦绝对路径和 `..`，`.minicc/allowlist.json` 是工作区内普通相对路径，acceptEdits 模式下一次 `write_file` 即拿到全部 bash/webfetch 权限。`fs.py:30` 的 `_is_sensitive_path` 只按文件名匹配，`read_file('.minicc/web_token.json')` 原样返回 bearer，`.minicc/mcp.json` 的 headers 同样可读。把 `.minicc/` 下认证/授权/凭据文件纳入敏感路径集合：写拒绝、读脱敏，按完整路径后缀匹配。
  验收：回归测试——acceptEdits 下 `write_file('.minicc/allowlist.json')` 被拒；`read_file('.minicc/web_token.json')` 不返回 token 原文；`read_file('.minicc/mcp.json')` 的 headers 值被脱敏；`read_file('.minicc/worker/*.config.json')` 被拒。

- **M2-T3 CLI always allow 不再写工具级通配（P1）** — `minicc/main.py:225-235`、`minicc/allowlist.py:60-100` 与 `:160-175`
  改什么：`main.py:227` 的 `kwargs = {"tool": name}` 恒含 tool 键，批准一次 `bash python -m pytest` 后 `rules["tools"] == ["bash"]`，后续任意 bash 全部自动放行。改为只记 `command=` / `path=` 具体值；工具级通配仅在用户显式选择「始终允许该工具全部用法」时写入并打审计事件。
  验收：批准一次 `bash python -m pytest` 后 rules 不含 `bash`（仅含具体 command），随后 `del /f /s /q` 必须重新询问。

- **M2-T4 allowlist 读-改-写竞态、固定临时名与明文落盘（P2）** — `minicc/allowlist.py:72`、`:160-175`
  改什么：`save_allowlist` 无任何锁且用固定 `.tmp` 名（已实测 8 线程全部 `PermissionError`、8 个 session 只有 2 个存活）；`add_session_rule` 存原始命令（含 Bearer token）而 `match_session_allowlist` 比对脱敏副本，导致 always allow 永不命中同时密钥落盘。改为 RLock + 每进程唯一临时名 + 存脱敏后的命令。
  验收：8 线程 ×20 次 `add_session_rule` 无异常且 8 个 session 规则全部存活；批准一次 bash 后 allowlist 文件不含 `sk-` 或 `Bearer` 明文；同一命令第二次命中 always allow 不再询问。

- **M2-T5 plan 模式 DAG 节点绕过 permission_mode（HIGH）** — `minicc/web.py:1130-1145`、`minicc/task_manager.py:69-70`、`minicc/audit.py:142-155`、`minicc/tools/bash.py:90-106`
  改什么：`task_manager.py:69-70` 的 `READONLY_PLAN_KINDS` 含 `exec`、`READONLY_PLAN_TOOLS` 含 `bash`；`web.py:1135` 的 `node_allow` 调 `authorize_tool` 时不传 `permission_mode`，落到 `audit.py:151` 的 `is_readonly_command`，而 `bash.py:106` 对 `argv[0]==pytest` 直接返回 True，`pytest -p <mod>` 即任意代码执行。修法：`node_allow` 传 `permission_mode`；把 `exec` 移出 `READONLY_PLAN_KINDS` 或禁止只读 DAG 节点声明 bash；`is_readonly_command` 对 pytest 做 argv 白名单（拒绝 `-p` / `-c` / `--rootdir` 与工作区外路径）。
  验收：回归测试——plan 模式下 planner 返回 `exec` + `bash` 节点必须被 `node_allow` 拒绝并产生 `status=denied` 审计事件；默认模式下合法只读 exec 节点仍可执行；`pytest -p json`、`pytest -c C:/evil/pytest.ini`、`pytest C:/other/repo/tests` 在 default 模式下不再自动放行。

- **M2-T6 junction / 符号链接越界（P2）** — `minicc/tools/fs.py:155-175`、`minicc/web.py:430-445`
  改什么：`fs.py:161` 用 `rglob()` 枚举后不复查 `resolve().is_relative_to(workspace)`，junction 下 grep 返回 `out/secret.txt` 的敏感内容；`web.py:435` 的 `/api/files` `walk()` 只信 `is_symlink()`（Windows `mklink /J` 返回 False），实测返回外部条目名称与大小并喂给 @-mention 索引。统一改为 resolve 后 `is_relative_to` 复查；并给 grep 加 2MB 文件大小上限。
  验收：回归测试——workspace 下建 junction 指向含 `secret.txt` 的外部目录后，grep、glob、tree、file_tree 四条路径均不出现该条目；正常深层目录枚举行为不变；`Editor._resolve` 现有越界语义不变。

- **M2-T7 MCP spawn 门控提前到此 milestone（MEDIUM）** — `minicc/mcp.py:105-130`、`minicc/tools/editor.py:185`、`minicc/audit.py`
  改什么：`mcp.py:116` 的 stdio spawn 继承整个父环境（含 LLM api_key 与 web bearer token），而 `.minicc/mcp.json` 是 agent 可写的工作区相对路径，一次 `write_file` 就把后续每个任务变成持有密钥的任意命令执行，plan 模式下也如此且无审计。改为 scrubbed env（PATH + 条目显式 env）+ spawn 审计事件，并把 `mcp.json` 纳入 M2-T2 的敏感文件集合。
  验收：写入 command 为 curl 外部地址的 `mcp.json` 被拒；已存在的恶意条目启动时子进程 environ 只含 PATH 加显式 env（断言 `MINICC_API_KEY` / web token 不在其中），并产生一条 spawn 审计事件。

- **M2-T8 顺手修额度 #1：config.py 的配置劫持与 .env 失效** — `minicc/config.py:171`、`:181`
  改什么：`pick()` 用小写 file_key 查 `os.environ`（Windows 大小写不敏感，环境里一个 `MODEL=` 就劫持配置并推翻文档的 .env 优先 config file 优先级）；`.env` 解析了但不导出到 `os.environ`。提前到此 milestone 的理由：M2/M3 的验证命令本身依赖 `MINICC_ALLOW_PRIVATE_FETCH`、`MINICC_TASK_EXECUTOR`、`MINICC_WEB_TOKEN`、`MINICC_FAKE_PROVIDER` 等开关，若它们走 .env 不生效或被任意 `MODEL=/API_KEY=` 劫持，安全测试本身可能假绿。
  验收：Windows 下环境里的 `MODEL=` 不再劫持 `.env`/config file 的 model；`MINICC_ALLOW_PRIVATE_FETCH` 写进 `.env` 后生效；各一条回归。

### M3 凭据、网络与进程面（4 周，依赖：M2）

**目标**：收紧谁能驱动这个 agent、agent 能把什么发到网上，并修掉任务编排层三个会永久卡死或损坏状态的缺陷。

**退出标准**：
1. `tests/test_web_security.py` 新增 Origin/CSRF 与网络门用例，`tests/test_task_durability.py` 新增租约与会话并发用例，全部先红后绿；
2. 人工核查：从非回环 Origin `POST /api/tasks` 返回 403 且不创建任务；`MINICC_TASK_EXECUTOR=process` 并发跑 2 个任务并强杀 worker 后 `.minicc/worker/` 无 `config.json` 残留且任务可被 auto-resume 重新排队；
3. `grep -rn sk-` 在 `.minicc/` 与服务器日志无命中。

**任务**：

- **M3-T1 do_POST 增加 Origin/CSRF 校验（P1）** — `minicc/webserver.py:360-400`、`minicc/webauth.py`
  改什么：`webserver.py:377` 从不校验 Origin（`_request_origin()` 只用于回写 CORS 头），`WebAuth.check` 在 `required=False`（默认回环）时直接 `return True`，任意已打开的网页可发 cross-site POST 到 `/api/tasks` 并在 payload 带 `permission_mode: "yolo"` 全放行。改为对状态变更方法强制 Origin 缺失或回环/同源，否则 403（非浏览器客户端保留显式关闭开关）。
  验收：带 `Origin: http://attacker.local` 或 `http://evil.example` 的 `POST /api/tasks` 返回 403 且不创建任务；无 Origin 的同源请求仍可用；388 用例不回退。

- **M3-T2 CORS 回环判定过宽加 SSE token 泄漏（P1）** — `minicc/webauth.py:25-45`、`minicc/webserver.py:70-85`、`web/src/core/state.js:50-60`、`web/src/core/transport.js`
  改什么：`webauth.py:32` 把 `LOOPBACK_SUFFIXES` 里的 `.local` 当回环（`.local` 是 mDNS/link-local，会解析到局域网其他机器），攻击者页面可拿到 ACAO 跨站读任务历史并驱动 `/api/tasks`，而默认回环绑定不需要 token。SSE token 走 query string（`state.js:54`），`webserver.py:76` 的 `log_message` 原样打印 `self.path`，把 bearer token 写进 `.minicc/web-<port>.stdout.log`。改为 `LOOPBACK_SUFFIXES` 去掉 `.local` 只保留 `.localhost`；SSE 不再接受 query string token（401），改 header 或首帧；日志不再原样打印 path。
  验收：`Origin: http://foo.local` 不再拿到 ACAO；SSE query token 返回 401；访问 `/api/files` 后 stdout 日志不含 token 与完整 query；前端 SSE 仍能连接（transport smoke 通过）。

- **M3-T3 SSRF 防护加 IP 钉扎（P1）** — `minicc/netguard.py:20-60`、`minicc/tools/webfetch.py:150-175`、`tests/test_webfetch.py:105-125`
  改什么：`netguard.py:27` 用 `getaddrinfo` 校验一次，`webfetch.py:159` 连接时 urllib 再解析一次，TTL=0 的 rebinding 主机可让校验看到公网 IP 而连接落到 127.0.0.1 或 169.254.169.254。`tests/test_webfetch.py:111` 唯一的重定向测试开了 `MINICC_ALLOW_PRIVATE_FETCH=1`，等于关掉守卫测重定向。改为解析一次后钉死 IP（socket 级连接 + Host 头），逐跳重解析校验。
  验收：回归测试——rebinding 场景（首次解析公网 IP、再次解析 127.0.0.1）下 webfetch 拒绝连接；重定向逐跳校验测试在不设 `MINICC_ALLOW_PRIVATE_FETCH` 的情况下通过（`grep` 确认测试文件无此 env）。

- **M3-T4 网络门控从子串黑名单改为 argv 感知（P1）** — `minicc/audit.py:15-45`
  改什么：`audit.py:19` 的 `command_uses_network` 只做子串匹配，已实测 `pip3 install`、`pip download`、`apt-get install`、`go get`、`cargo install`、`docker pull`、`ssh`、`scp`、`rsync`、`npm i`、`pnpm i`、`git  clone`（双空格）全部判 False，`allow_network=False` 时照样出网。改为 argv 分词 + 已知网络命令集合。
  验收：表驱动单测 ≥20 条，`allow_network=False` 时全部判为需要授权；`git status` 与 `pytest` 仍判 False。

- **M3-T5 heartbeat_lease 能复活已过期租约（P1）** — `minicc/task_store.py:124-131`、`minicc/task_manager.py:1000-1030`
  改什么：`task_store.py:124-130` 的 UPDATE 没有 `AND expires > ?` 栅栏（`claim_lease` 有），TTL 过后心跳仍返回 True 并把 expires 再推 45s，`has_live_worker` 把死亡 worker 报成存活，auto-resume 拒绝重排队，任务永久卡死。补上栅栏（一行）。
  验收：回归测试——租约过期后 `heartbeat_lease` 返回 False，`has_live_worker` 报该 worker 死亡，auto-resume 能重新排队同一任务；连续两次并发 resume 不会双跑。

- **M3-T6 detached worker 不再把明文 api_key 落盘（P1）** — `minicc/task_manager.py:1690-1720` 与 `:1780-1800`、`minicc/task_worker.py`
  改什么：`task_manager.py:1702` 每个进程模式任务把明文 api_key 写进 `.minicc/worker/<task_id>.config.json`（0600），只有子进程成功读到后才删；租约认领失败、硬杀、崩溃、重启都会永久留下明文密钥，父进程 finally 只删 cancel_file。`:1790` 的进程句柄路径从不复查租约。改为经 stdin/管道传密钥 + 父进程 finally 兜底删除 + 启动时清扫过期 worker config + 进程句柄存活期间周期性复查租约。
  验收：process 模式下强杀 worker 或让租约认领失败后 `.minicc/worker/` 无 `config.json` 残留；worker 正常退出路径功能不变；租约失效后任务被重新排队。

- **M3-T7 SessionStore 并发写损坏会话 JSON（P1）** — `minicc/session.py:210-235`
  改什么：`session.py:220` 用固定 `.tmp` 名，web 的 `_session_lock` 是进程内锁而 worker 子进程有自己的空锁表，已实测两个并发 `save()` 双双抛 `WinError 32` 且 session 文件消失，而 `MINICC_TASK_EXECUTOR=process` 是文档化模式。改为每进程唯一临时名 + 原子替换 + 跨进程文件锁。
  验收：回归测试——2 个进程/线程对同一 session `save()` 20 次，无异常、无文件丢失、最终 JSON 可解析且包含双方写入；process 模式下同样通过。

- **M3-T8 _rpc_threads 无界增长（MEDIUM）** — `minicc/web.py:270-290`
  改什么：`web.py:278` 用客户端任意 key 无限增长，每个 body 可达 `MAX_BODY_BYTES`，默认回环绑定无需认证，任何本地页面可无限膨胀 workbench 进程堆。改为有界插入序缓存（上限 512，逐出最旧，镜像 `static_assets._CACHE`）+ thread_id 模式与长度校验。
  验收：连续 2000 次 `thread/start` 用随机 8KB thread_id，堆中记录数不超过 512 且旧条目被逐出；超长或非法 thread_id 返回 400。

- **M3-T9 批量任务与快照写入缺陷（P2）** — `minicc/task_manager.py:1014`、`:1404`、`minicc/task_persistence.py:56`
  改什么：auto-resume 把 batch 父任务当普通任务重跑，丢失全部子任务 prompt；批量附件按子任务数重复落盘且永不清理（16 子任务 × 12MB ≈ 204MB/次）；`close()` 第一个 flush 抛错就放弃其余终态 flush。三处分别修复。
  验收：16 子任务批量中断后 auto-resume 恢复时子任务 prompt 全部在位；单次批量附件落盘总量不超过 1 份；snapshot flush 首个失败后其余终态仍落盘。

### M4 证据链与评测可信度（5 周，依赖：M1, M2）

**目标**：在动任何能力之前，先把 agent 到底行不行变成可度量、可复现、CI 能拦截的事实。三个空洞：唯一 e2e 检测不到任务链路损坏、整个 HTTP 面与默认 MCP 传输零测试、pass@1 分母只有 3 且 edit 类 fixture 从未验证实际编码。同时先修证据链本身——28/30 完成率建立在可绕过的验收门与分母只有 3 的 pass@1 上，不修则后续效果无法度量。

**退出标准**：
1. 四项证据链回归：bash 修改文件后 `verification_required=True` 且 verifier 实际执行；改 `.md/.sh/Makefile` 后旧指纹不复用；100 个 write 事件加 5 个 trace 的会话里 event-1 仍可被引用；零工具调用的只读任务无法只用 trace id 判 complete；
2. 变异测试写进 CI：把 `MINICC_BASE_URL` 指向不可达地址（保留 `MINICC_FAKE_PROVIDER=1`）时 `npm run test:web` 退出码非 0；正常 fake provider 下通过且断言包含任务终态与至少一次工具证据；
3. 新增 `tests/test_http_surface.py`，POST `/api/*` 路由 Python 测试覆盖率 100%，`rpc.py` 分发器 ≥10 个 method 独立单测；
4. `python -m minicc.benchmarks --suite v2` 输出 `grading_coverage=1.0`、pass@1 分母 ≥24（其中 edit 类 ≥10），`docs/BENCHMARK_EVALUATION.md` 由脚本重新生成并附运行命令与日期；
5. A/B 对比器 gate 违反时 exit code 1，且 CI 用构造数据验红；`latency_p50_ms=115s` / `latency_p95_ms=826s` 基线写入 `docs/BENCHMARK_EVALUATION.md`；
6. 任务结束事件带 `cost_usd`，CLI `/cost` 打印本会话费用与 token 分解；未知模型 `cost_usd` 为 None 且 `cost_available` 如实反映；
7. `python -m pytest -q -W error` 通过；PR 评测门 ≤15 分钟，真实模型评测只进 nightly。

**任务**：

- **M4-T1 先修证据链（P0/P2，否则评测数字无意义）** — `minicc/agent/loop.py:60-75`、`minicc/agent/verification_plan.py:65-80`、`minicc/agent/completion.py:250-265` 与 `:418-435`
  改什么：`loop.py:66` 的 `WRITE_TOOL_NAMES` 只有 `{write_file, edit_file, worktree_create, worktree_remove}`、不含 `bash`，agent 用 `sed -i` 或 `python patch.py` 改工作区时 `verification_required` 永不为 True，确定性 verifier 不跑、`completion.py:262` 的写后证据检查不触发；`verification_plan.py:73` 的 suffixes 白名单漏 `.md/.sh/.ps1/.svg/.png` 与无扩展名文件（Makefile/Dockerfile），改了这些文件后旧的通过缓存仍被复用；`completion.py:256` 只校验证据 id 存在性，node_entered 的 trace 事件可冒充验收证据（零工具调用的只读任务引用 event-1 即可判 complete）；`:426` 的最新 80 条全局截断把早期 write/verification 事件逐出，与注释意图相反，连续 3 次 continue 后 `web.py:1656` 直接判任务失败。四处分别修：`WRITE_TOOL_NAMES` 增加 bash（按命令是否可能改写工作区判定）；suffixes 补全；`available_ids` 只收 `kind in {tool, verification}` / write / error；证据包改分类配额（保留最早 N 条 write/verification + 最新若干）。
  验收：EXIT 1 的四项回归各一条命名测试。

- **M4-T2 web_smoke 变成真正的端到端断言（P0）** — `tests/web_smoke.mjs:270-300`、`.github/workflows/ci.yml`
  改什么：`:285-296` 提交任务后只断言「出现了 loading 元素 + 无 console error」，实测把 provider 指向不可达地址跑依然打印 passed，submit → provider → agent loop → verifier → completion judge 全链路回归不可见。改用 `MINICC_FAKE_PROVIDER` 走完整链路并断言终态与工具证据，另加一条 provider 不可达必须失败的负向用例。
  验收：EXIT 2 的变异测试作为独立 CI step。

- **M4-T3 补齐 Web HTTP 面与 RPC 的 Python 测试（P0）** — 新增 `tests/test_http_surface.py`、`minicc/web.py`、`minicc/agent/rpc.py`
  改什么：`grep api/tasks tests/*.py` 为 0 命中；`/api/tasks/batch`、`/api/events`、`/api/rpc`、`/api/audit`、`/api/worktrees`、`/api/mcp`、`/api/changes`、`/api/workspace/*` 全部无 Python 测试；`rpc.py`（140 行分发器）只有 `web.py:67` 导入、无任何测试导入。新建测试起真实 `ThreadingHTTPServer` 打真实请求。
  验收：每个 POST `/api/*` 路由至少一条（覆盖 200/400/401/403 与 workspace_roots 越界与并发）；`rpc.py` 分发器 ≥10 个 method 独立单测；`pytest tests/test_http_surface.py -q` 全绿且 < 20s。

- **M4-T4 价格表与美元成本核算（能力差距 S 项，提前至此）** — 新增 `minicc/pricing.py`；`minicc/llm/usage.py:45-60`、`minicc/agent/state.py`、`minicc/benchmarks.py:103`、`minicc/web.py`、`minicc/main.py`、`web/src/panels/index.js`
  改什么：`usage.py` 有诚实 token 计数但无价格表，无 `/cost`、无每任务费用。补 per-model 输入/输出/缓存读/缓存写单价表（可配置、按 model 前缀匹配、未知模型显式 None 不猜）；`add_usage_totals` 输出 `cost_usd` 并落进每行 result、任务快照、前端面板与 CLI `/cost`。提前到此 milestone 的理由：M1 刚修好 Anthropic 缓存记账，$/task 几乎是免费副产品，而 M6 的 fan-out 护栏只有 token 口径，一旦阈值调错没有美元报警。
  验收：`tests/test_pricing.py` 用固定 usage 断言 `cost_usd` 精确到 1e-6、未知模型为 None；fake provider + 显式单价跑 1 条任务后 `cost_per_success_usd` 非 None；缓存命中部分按 cache_read 折扣价计；日志与快照不含 api_key。

- **M4-T5 fixture 工作区 + edit fixture 真编码 + hidden grader（修正版）** — `benchmarks/tasks.json`、新增 `benchmarks/fixture-workspaces/`、新增 `benchmarks/tasks.v2.json`、新增 `minicc/bench_tasks.py`、`minicc/benchmarks.py:300-345`、`minicc/behavior_bench.py`
  改什么（含一处前提修正）：fixture 类任务的隔离**已经存在**——`benchmarks.py:306` 为 fixture 任务创建了独立 `tempfile.TemporaryDirectory`，`prepare_fixture()`（`behavior_bench.py:115`）只写入 `task["fixture"]` 里的坏起始代码且有路径逃逸校验，grader 规格经 `stdin` 以 `json.dumps(grader)` 喂给子进程（`behavior_bench.py:105`）。**不存在的缺陷不要修**。真正缺的是：30 条 legacy fixture 里 0 条带 `fixture` 字段、`allow_changes` 全为 None（`benchmarks.py:334` 的 `allow_changes=bool(task.get("fixture"))`），所以 agent 实际跑在 minicc 仓库本身上，编码能力从未被度量、也无法安全打开写权限。因此本任务做的是：为 edit 类 fixture 建小型合成仓库，增加 `file_contract` / `command_contract` 两类 grader，新增 `--grader-dir` / `MINICC_EVAL_GRADER_DIR` 把 `.graders` 移到仓库外加载，并在隔离工作区内打开 `allow_changes=True`。
  验收：`--suite v2`（不带 `--run`）输出 `grading_coverage=1.0`、pass@1 分母 ≥24；新增 ≥20 条可写任务（≥8 条真写文件、4 条跑测试修 bug、4 条多文件）；`tests/test_bench_tasks.py` 校验 schema、id 唯一、fixture 路径不逃逸、grader 类型白名单、`max_minutes` 为正，并用 fake provider 跑 2 条 file_contract fixture 断言一过一败（验证 grader 不恒真）；`test_grader_unreadable` 断言 `read_file/grep/glob/tree` 读 `.graders` 全部返回 TOOL_ERROR；手动跑 2–3 条真实模型 edit fixture，输出含 verification 事件与 completion 判定，且工作区外无任何写入（`git status` 校验隔离目录干净）。

- **M4-T6 A/B 对比器与统计门槛** — 新增 `minicc/bench_compare.py`；`minicc/benchmarks.py`（`--variant/--baseline/--repeat/--gate/--junit-out`）；新增 `tests/test_bench_compare.py`
  改什么：M4 只有绝对指标，无法回答「这次改动到底有没有效果」，而 36 周的迭代全部依赖这个判断。新增 compare 子命令：两次 run 的 JSON 逐任务对齐，输出 pass@1 差值 + Wilson 95% CI、cost 差值 + bootstrap CI、P50/P95 延迟差值、按 category 分解；`--gate` 支持 `pass_at_1` / `cost_per_success_usd` / `latency_p95_ms` / `grading_coverage` 四类阈值，违反 exit 1；`--repeat N` 支持 pass@k，N<10 不下结论。
  验收：构造 12 任务两版结果，断言 CI 计算与手算一致、gate 违反时 `main()` 返回 1；CI 用构造数据验红（把阈值临时调到不可能满足时必须红）；`python -m minicc.benchmarks compare --baseline a.json --variant b.json` 输出人工可读 delta 表。M6 起每个能力 PR 必须附带 compare delta 表。

- **M4-T7 检索决策门（把非目标变成可证伪）** — `minicc/agent/retrieval.py`、新增 `benchmarks/retrieval-hitrate.json`、`minicc/benchmarks.py`（`--suite retrieval`）
  改什么：`retrieval.py` 是确定性 token+path+symbol 打分，docstring 自述「不是向量数据库」。不直接上 embedding：先定义 hit-rate 指标（对 N 个已知答案的定位任务，检索 top-k 是否包含目标文件/符号），用现有 12 条行为任务 + 30 条 fixture 的 trace 建基线；只有 lexical 基线的 `recall@5 < 0.6` 才引入本地 embedding（sentence-transformers 本地推理，不用外部向量库，尊重项目 §6 非目标），且必须有 A/B 对比数据。
  验收：`python -m minicc.benchmarks --suite retrieval` 输出 `recall@1/@5` 与 MRR；CI 记录数值但不门禁（首轮只建基线）；产出明确书面结论（达标则写下「不引入向量检索」并停止投入）。

- **M4-T8 CI 卫生** — `.github/workflows/ci.yml`、`pyproject.toml`、`tests/codex_smoke.mjs`
  改什么：CI 从不执行 3 个已签入的 Playwright 套件；`tests/codex_smoke.mjs` 无 runner 且引用不存在的 `tests/zombie_spawn_smoke.mjs`，完全孤立；pytest 跑 `-qq`（`addopts="-q"` + `ci.yml -q` = -2 级）无通过计数、无 warnings 汇总、无 `filterwarnings`、无 JUnit artifact、无 xdist；`httpx` 未进 dev extra 却被 16 个测试依赖（靠 `openai` 传递依赖侥幸存在）。改为 PR 评测门 <15 分钟（只跑 `--suite smoke` fake provider）+ nightly 真实 key 跑 `--suite v2 --repeat 2 --gate`；5 个套件全进 CI；pytest 改 `-ra` + 上传 JUnit + warnings 汇总；`httpx` 进 dev extra（`pip check` 校验）；删除孤立的 `codex_smoke.mjs`。
  验收：CI 可见 PR/nightly 两个 eval job；把 gate 阈值临时调到不可能满足时 nightly 必须红并附 artifact；CI 日志有 passed 计数与 warnings 汇总；`pip install -e .[dev]` 后能收集全部测试。

- **M4-T9 清理与文档可信度** — 仓库根若干、`web/assets/`、`web/app.min.js`、`docs/BENCHMARK_EVALUATION.md:46`、`README.md:192`、`minicc/__init__.py`、`minicc/main.py`、`minicc/mcp.py` clientInfo、`pyproject.toml`
  改什么：删除仓库根 `repro_budget.py`、`repro_id_collision.py`、`prev_test.txt`、`testlist.txt`、`pytest_full.log`、`pytest_full.err`、`pytest_verify.log`、`.tmp_audit_repro/`；`web/assets/` 只保留 manifest 引用的 1 份（删 20 个陈旧内容 hash bundle 与未引用的陈旧 CSS）+ CI freshness 检查；删被 gitignore 且无人引用的 `web/app.min.js`；`docs/BENCHMARK_EVALUATION.md:46` 的「23 项通过」改为由脚本生成；`README:192` 引用 package.json 里不存在的 `npm run typecheck` 改为真实脚本；版本号四处不一致（pyproject 0.1.0 / `main.py` 硬编码 / MCP `clientInfo` 0.2.0）统一到 `minicc/__init__.py.__version__`。
  验收：仓库根无 repro/testlist/pytest log 文件；`web/assets/` 只剩一份；`npm run check:web` 与 CI freshness 检查通过；`python -c "import minicc; print(minicc.__version__)"` 与 pyproject 及 MCP clientInfo 一致；`docs/BENCHMARK_EVALUATION.md` 数字与命令输出逐字一致。

### M5 MCP 桥加固与 CLI 接线（3 周，依赖：M2）

**目标**：MCP 的 6 个缺陷全集中在 `mcp.py` 这个零测试的默认传输层。桥对服务器的信任度远高于代码库其他部分对工具输出的信任度：无截断、无 id 类型容错、无 reader 监督、无环境净化、无重收割。

**退出标准**：
1. 新增 `tests/test_mcp_stdio.py` ≥8 条表驱动单测；
2. 50 万字符 MCP 输出被截到 ≤6000 且 `truncated=True`；string id 正常返回；stdout 含不可解码字节时 reader 不死、客户端标记 dead 且后续调用 <1s 失败而非 30s；
3. CLI 在有 `mcp.json` 的工作区 `/tools` 列出 `mcp__` 工具（否则 README:24 相关表述删除）；
4. `/api/chat` 对一个坏 `mcp.json` 条目返回结构化 McpError 而非 500 ValueError。

**任务**：

- **M5-T1 render() 输出截断（HIGH）** — `minicc/mcp.py:185-200`
  改什么：`:192` 的 `render()` 直接 `"\n".join(chunks)`，50 万字符直入 prompt 和 session JSON，违反所有内置工具遵守的 6000 字符预算。走 `split_output()` 设 head/tail/truncated。
  验收：假服务器返回 500k 字符，`ToolResult.output` 字符数 ≤6000 且 `truncated=True`；工具输出 ≤6000 字符的比例作为常驻指标 = 100%。

- **M5-T2 id 类型容错与解析失败全包 McpError（HIGH）** — `minicc/mcp.py:240-270`、`minicc/tools/__init__.py:137`、`minicc/web.py:172`
  改什么：`:262` 对合法 JSON-RPC string id 抛裸 `ValueError`，而 `web.py:172` 只 `except McpError` → 整个 workspace 每个请求 500「agent failed: ValueError」；`:148-149` 服务器主动请求（roots/list、ping）被丢弃不答。改为两种传输都 `str(a)==str(b)` 比较；所有解析失败包成 `McpError`；对服务器主动请求给出响应或明确日志。
  验收：string id 的 HTTP 与 stdio 请求均正常返回并成功调用；坏 `mcp.json` workspace 的 `/api/chat` 返回结构化错误而非 500；假服务器发 ping 得到应答。

- **M5-T3 stdio reader 监督与负缓存（MEDIUM）** — `minicc/mcp.py:110-200`、`:340-360`
  改什么：`:143` stdout 以 `encoding="utf-8"` 打开无 `errors="replace"`，reader 线程遇不可解码行即死；`_request` 只在入口检查 liveness（`:158` `self.process.poll() is not None`），之后每次调用阻塞满 30s；`McpManager` 不负缓存（`:350-356` 每任务重新 spawn）。改为 `errors="replace"` + 读循环包裹 + reader 退出即标记 client dead + 快速失败 + Manager 负缓存。
  验收：假服务器输出不可解码字节后，第一次调用失败且第二次调用 <1s 失败；两次任务之间不重复 spawn；单次 MCP 调用 P99 < 5s（此前中毒后恒为 30s）。

- **M5-T4 工具名 128 字符截断与冲突（MEDIUM）** — `minicc/mcp.py:340-390`
  改什么：`:381` 工具名 128 字符截断与冲突抛未捕获 `ValueError`，同样绕过 `web.py:172` 的 `except McpError`。改为短哈希后缀（server+tool）或在 `tool_specs()` 内检测重复并抛 McpError 点名双方。
  验收：两个仅在第 128 字符后不同的长名不再抛未捕获 ValueError 而是明确的 McpError。

- **M5-T5 close() reap 子进程与部分启动失败（LOW）** — `minicc/mcp.py:190-200` 与 `:340-360`
  改什么：`:196` 的 `close()` 只 `terminate()` 不 wait/kill、不关管道，POSIX 上成僵尸、SIGTERM-ignoring server 继续跑；`tool_specs()` 无 try/finally，第二个 server `list_tools()` 抛错时第一个 child 无主。改为 `terminate → wait(timeout) → kill → wait` + 关闭 stdin/stdout + try/finally。
  验收：`close()` 后子进程被 reap、无僵尸；第二个 server 启动失败时第一个子进程被回收。

- **M5-T6 CLI 接入 MCP 或修正 README 承诺** — `minicc/main.py:400-445`、`minicc/tools/__init__.py`、`README.md:24`
  改什么：`main.py:407` 调 `build_registry(editor, yolo=config.yolo)` 不传 `mcp_manager`，`main.py` 零 mcp import，而 README:24 把 stdio MCP 写成 CLI 特性（实际 web-only）。在 M2-T7 的 spawn 门控落地后补齐 CLI 接线（约 10 行），让文档与实现一致。
  验收：在有 `mcp.json` 的工作区跑 CLI，`/tools` 列出 `mcp__` 工具；无 `mcp.json` 时行为与现在完全一致（现有测试不回归）；若选择不接，README 与 docs 中相关表述已删除且无一处声称 CLI 支持 MCP。

- **M5-T7 MCP resources/prompts 与工具健康检查（partial gap 补强）** — `minicc/mcp.py`、`minicc/tools/__init__.py`
  改什么：MCP 无 resources/prompts/sampling、无工具健康检查与配额。补 `resources/list`、`prompts/list` 作为只读上下文注入并有界；补工具健康检查（不可用 server 被标记而非每次调用卡超时）。`sampling` 显式延后（理由见第四节）。
  验收：假服务器 `resources/list` 结果作为只读上下文注入且 ≤6000 字符/条；标记为不可用的 server 后续调用立即返回结构化错误。

### M6 能力扩展 I：有界可写委派与后台执行（5 周，依赖：M4, M5）

**目标**：在地基可信之后做第一个真正的能力扩展：从只读侦察子代理到有界可写委派，并补上商业产品标配的后台 shell，同时把串行的写/exec 变成可并行。这是唯一显式标注 XL 风险的阶段：并行写 + 合并冲突 + 失败传播的组合会重新打破 M1–M4 修好的一致性保证。缓解：默认关闭、配置开关启用；先只允许按文件不重叠的并行写；合并前强制跑 verifier；任一子代理失败即整体失败并保留 worktree 供人工检查。

**退出标准**：
1. 新 benchmark 任务（跨 3 个文件的改造）由 2 个可写子代理并行完成：pytest 全绿、verifier 通过、父会话 `validate_tool_protocol` 通过；
2. 超预算任务确实触发软收束并最终以 `BudgetExceeded` 结束；
3. 后台 shell 任务可轮询输出、取消后子进程被终止；`bash start /m &` 仍被拒绝；
4. 30 条 fixture 重跑，token/task 与 P95 不劣于 M4 基线超过 15%（否则回退 fan-out 阈值）；
5. write 子代理默认只允许跑在 acceptEdits 或显式批准的会话里，且子代理 prompt 明示「子代理结果不可信」。

**任务**：

- **M6-T1 subagent 可写档加有界深度与预算（XL 核心）** — `minicc/agent/subagent.py:30-60` 与 `:140-170`、`minicc/tools/registry.py`、`minicc/agent/state.py`
  改什么：`subagent.py:36` 的 `SUBAGENT_TOOLS` 排除 write/edit/bash/task，深度 1、并发 3、父线程 `future.result(timeout=600)` 阻塞。改为分层工具集（readonly / write-scoped / exec-scoped），深度上限 2、并发上限 3，**仍排除 task 工具**（结构上不可能递归，直接对抗「无约束递归多 Agent」非目标），每个子代理带显式 Budget 且继承父级 `permission_mode` 与 `allow_network`，结果按不可信 tool result 回传。
  验收：单测——三层工具集分离，exec 层必须显式授权且继承 permission_mode；子代理 spec 里不存在 task 工具（结构断言）；深度 2 的嵌套在第 3 层被拒；并发第 4 个被 BoundedSemaphore 拒绝并返回可读错误而非挂起；子代理 budget 到限时以 `BudgetExceeded` 结束并回传结构化失败，不拖垮父任务。

- **M6-T2 子代理进度可见、可取消、计入父预算** — `minicc/agent/loop.py`（task 工具调用点）、`minicc/web.py:1145-1180`、`minicc/agent/state.py:60-80`
  改什么：`future.result(timeout=600)` 完全阻塞，web 上看不到子代理在干什么；`web.py:1166` 的 `run_node` 用全 None 的 Budget，`soft_max_tokens` / `soft_max_duration_seconds` / `max_turns` 在 DAG 阶段全部失效，4 个并发节点各是一次无上限 `run_agent`。改为有界等待；`on_trace` 事件以带 `parent_id` 的形式冒泡到 web 事件流；`run_node` 传受控 Budget（沿用 `runtime_state.budget` 的 soft 上限）；`execute_dag` 结束后把 `token_totals` 回填 `record_usage`。
  验收：`tests/test_subagent_streaming.py`——fake provider + 假 SSE 收集器断言收到 ≥3 条子代理事件；DAG 节点超 `soft_max_tokens` 时返回 `budget_exceeded` 而非继续跑；DAG 执行后 `runtime_state.budget.tokens` 反映全部节点总消耗。

- **M6-T3 写/exec 工具并行执行** — `minicc/agent/loop.py:962` 一带、`minicc/tools/registry.py`
  改什么：`loop.py:962` 只有只读调用 fan out（`asyncio.to_thread`），`write_file`/`edit_file`/`bash` 仍串行，多文件改造任务 latency 全花在等 IO。改为按依赖分组并行：同一轮内对不同 path 的写并行，bash 与写并行需保持「写先于读」的偏序。
  验收：`tests/test_parallel_writes.py`——fake 工具各 sleep 0.3s，一轮 4 个不同 path 的 `write_file` 断言墙钟 <0.6s（串行基线 >1.2s）；同 path 的两个 `edit_file` 仍串行且第二个看到第一个的结果；并行写失败一个不影响其余结果收集。

- **M6-T4 后台 shell（异步执行 + 输出轮询 + 取消传播）** — `minicc/tools/bash.py`、`minicc/tools/schemas.py`、`minicc/agent/loop.py:60-75`
  改什么：`bash.py` 同步执行，`detached_command_reason()` 主动拒绝 `start/nohup/setsid/&`，长命令只能阻塞一个工具轮次或绕道。改为显式 `run_in_background` 参数 + 输出环形缓冲 + 轮询读取 + 取消传播（终止整个进程组），同时**收紧而非放宽**原有的 detached 拒绝。
  验收：单测加手工——启动 `python -c "import time;print(1);time.sleep(5)"` 立即返回 shell_id；`bash_output` 增量读到输出；`kill_shell` 后 poll 在 1s 内非 None 且无残留进程；输出落盘有界（≤6000 字符截断）；`bash start /m &` 仍被拒绝；后台 shell 计入审计事件。

- **M6-T5 跨文件并行写隔离与合并** — `minicc/agent/graph.py:222`、`minicc/worktree.py`
  改什么：并行写需要按文件粒度锁或 worktree 隔离，合并前冲突检查 + verifier。
  验收：集成测试——2 个子代理写同一文件时其中一个失败并报告冲突，工作区不留半成品；写不重叠文件时并行成功且父会话收到两份证据；任一子代理失败即整体失败并保留 worktree 供人工检查。

### M7 能力扩展 II：Hooks、slash 命令、交互审批、项目配置（4.5 周，依赖：M6）

**目标**：从一个 agent 变成一个可扩展的 agent 平台：hooks 是扩展原语，slash 命令/Skills 是用户侧定制，交互审批把 M2 的权限模型从「拒绝」升级为「询问」。

**退出标准**：
1. hooks 四条事件各一条集成测试（含超时与失败隔离）；
2. 自定义 slash 命令在 CLI 与 Web 都能触发并被权限模型覆盖；
3. Web 端一次真实交互审批：`should_allow` 挂起、前端弹窗、允许/拒绝、审计事件落库；60s 无响应自动 deny；
4. `.minicc/config.json` 的项目级覆盖生效且优先级文档化；新增的 CLI flag 出现在 `--help`；
5. 断网提交后 composer 内容完整恢复；@-提及一个文件后模型上下文出现该文件内容。

**任务**：

- **M7-T1 Hooks：PreToolUse / PostToolUse / UserPromptSubmit / Stop** — 新增 `minicc/hooks.py`、`minicc/config.py`、`minicc/agent/loop.py`、`minicc/tools/registry.py`、`minicc/web.py`
  改什么：仓库零实现。设计配置文件 schema（命令、匹配器、超时、失败策略），四条事件挂在 `loop.py` 与 `registry.py` 的执行前后；hook 以子进程运行、stdin 传 JSON、退出码约定；hook 输出一律按不可信数据处理并脱敏；hook 本身走 M2 的 workspace/权限校验，不允许访问 `.minicc/` 凭据文件（复用 M2-T2 的敏感路径集合）。缺省关闭。
  验收：集成测试——四条事件各触发一次且参数/返回值符合 schema；hook 退出码非 0 或超时（默认 5s）被 kill 且不阻断主流程（只记审计）；hook 抛异常不影响主流程；hook 无法读 `.minicc/web_token.json`；无 hooks 时零行为变化。

- **M7-T2 自定义 slash 命令加 Skills** — `minicc/main.py:320-380`、`minicc/prompt.py`、`minicc/config.py`、`web/src/chat/*`
  改什么：`main.py:332` 的 REPL 命令集硬编码封闭（`/help /tools /status /view /compact /collapse /expand /clear /exit`）。增加 `.minicc/commands/*.md`（项目级）与 `~/.minicc/commands/*.md`（用户级）发现机制，展开为 prompt 模板（支持 `$ARGUMENTS`），与 AGENTS.md 同等对待：只能作为工作约定，不能覆盖权限边界；Skills 目录（SKILL.md 按 description 自动注入相关技能说明）正文不常驻。
  验收：手工加单测——`.minicc/commands/` 放一个 `review.md`，CLI 与 Web composer 输入 `/review` 都展开为对应 prompt 并进入正常 agent 流程；命令内容不能覆盖系统指令或权限边界；Web composer 输入 `/` 出现自定义命令补全项。

- **M7-T3 Web 端交互式权限审批加声明式 allow/deny 规则** — `minicc/web.py:830-870`、`minicc/audit.py`、`minicc/allowlist.py`、`minicc/webserver.py`（SSE 帧）、`web/src/chat/stream.js`、`web/src/core/dialog.js`、新增 `.minicc/permissions.json`
  改什么：`web.py:845` 的 `should_allow` 只发审计事件后返回 `decision.allowed`，从不询问用户，且无声明式规则文件。实现审批请求经 SSE 推前端（独立帧类型 + 有界等待，防止审批请求把 task_event 流堵死）、超时默认拒绝、批量相似调用合并、声明式规则文件（deny 优先，与 hooks 同源权限模型），CLI 保留原有 y/N/a 交互。
  验收：手工验收——default 模式下 Web 提交需要 bash 的任务，前端弹审批窗，允许后执行、拒绝后工具返回 denied 并落审计事件；`.minicc/permissions.json` 的 deny 规则优先于 allow；60s 无响应自动 deny；已有 permission_modes 测试不回退；acceptEdits/yolo 下保持零打扰。

- **M7-T4 项目级配置层加 config.py 剩余 6 个缺陷** — `minicc/config.py:90-190` 与 `:255-265`
  改什么：config.py 只有 user 级（`~/.minicc/config.json`），约 30 个旋钮只有 6 个能走 CLI flag。加项目级 `<workspace>/.minicc/config.json`，把高频的 10 个暴露为 CLI flag；同时修该文件自身剩余缺陷：非对象 config.json 抛裸 AttributeError（`:165`）、`if value:` 丢掉显式 0/false（`:179`）、JSON 列表被 `str()` 成 Python repr（`:183`，workspace_roots 变成两个不存在的目录）、`_parse_env_file` 保留行内注释且不认 export（`:94`）、`home_dir()` 在 getter 里 mkdir（`:77`）、`describe()` 打印 api_key 头尾（`:145`）。
  验收：单测——`.minicc/config.json` 的键覆盖 user 级配置且优先级文档化（`.env` > 环境变量 > project > user，按现有文档口径）；`--model/--permission-mode/--max-turns` 等 flag 出现在 `--help` 且生效；6 个缺陷各一条回归（ConfigError 而非 AttributeError、显式 0/false 保留、列表不再变 repr、export 与行内注释正确、`MINICC_HOME` 指向已存在文件时抛 ConfigError、`describe()` 不含 api_key）。

- **M7-T5 前端数据丢失与 @-提及内容注入（MEDIUM）** — `web/src/chat/stream.js:225-250`、`web/src/panels/index.js`、`minicc/web.py`（`AgentService._run_chat` payload 组装）
  改什么：`stream.js:234` 在 POST `/api/tasks` 之前清空 composer，任何失败（服务重启、500、401、超时）都永久丢失用户输入的 prompt 与最多 4 张粘贴图片。先捕获 `draft` 与 `draftAttachments`，catch 里恢复并 `renderAttachmentTray()` 再弹 toast。另外 @-提及 popover 只把路径插进 prompt 文本，不注入文件内容；改为插入结构化引用，发送时按 token 预算注入 head（超预算截断并提示），越界路径（junction）被拒。
  验收：手工验收——停掉后端再提交，composer 文字与附件 tray 原样恢复并弹出错误提示；@-提及 `src/main.py` 后模型收到的 user message 含该文件前 N 行且带路径标注；超过 context 预算时截断并附 `[truncated]` 标记。

### M8 记忆、会话 fork、插件 API、可安装产物与可观测（6 周，依赖：M7）

**目标**：让项目从「能跑的仓库」变成「别人能装上、出问题能查、上次教它的事它记得」的产品。这是可靠性优先主干缺失的尾巴：M1–M7 交付的是「引擎与安全达到同级」，M8 才补齐 installability 与可观测。

**退出标准**：
1. 一个 10 条消息的会话在第 5 条 fork，两个会话文件独立，`--resume` 能列出并恢复 fork；
2. 任务 A 写一条记忆，任务 B 的系统提示出现该条目索引行；记忆文件可被用户手工编辑与删除；无记忆时行为不变；
3. `docs/PLUGIN_API.md` 里的示例代码可原样跑通；注册与内置同名的工具被拒（除非显式 `override=True`）；
4. 干净 venv `pip install dist/minicc-*.whl` 后 `minicc --version` 与 `minicc-web --workspace .` 均可用且 UI 200；版本号三处一致；
5. `MINICC_LOG_LEVEL=DEBUG` + `LOG_FILE` 下日志含 `provider_retry` / `tool_round_finished` / `run_finished` 且不含 api_key 与 web token；`minicc/` 下 `print()` 数量下降 ≥80%；`/api/metrics` 返回的 token/成本与单任务快照对得上；
6. `tests/test_core.py` 拆分完成且测试数不降、CI 墙钟不升。

**任务**：

- **M8-T1 长期记忆：MEMORY.md 读写工具加自动召回** — 新增 `minicc/agent/memory.py`（或 `minicc/tools/memory.py`）、`minicc/tools/__init__.py`、`minicc/prompt.py`、`minicc/session.py`
  改什么：当前跨 session 只有 AGENTS.md 常驻 prose + SQLite 历史关键词搜索。新增 `memory_write` / `memory_read` / `memory_list`，写 `~/.minicc/MEMORY.md` 与 `<workspace>/.minicc/MEMORY.md`，条目化（id/内容/来源/时间）；系统提示只注入条目索引（不注入全文，控制 token；≥200 条时只注入最近 50 条并标注省略），模型可显式召回；内容经 `redact_text` 脱敏后才落盘；检索继续用 `retrieval.py` 确定性打分。
  验收：`tests/test_memory.py`——任务 A 写一条记忆，任务 B 的系统提示里出现该条目的索引行；`memory_write` 拒绝写 `.minicc/` 下的敏感路径与绝对路径外路径；索引注入有上限；无记忆时行为不变。（不引入向量库，理由见 M4-T7 决策门。）

- **M8-T2 会话 fork / 分支** — `minicc/session.py`、`minicc/agent/context.py`、`web/src/chat/*`
  改什么：`session.py` 只能就地截断 + 单个 `.pre-rewind.json` 备份，无法从中间某条消息分叉探索不同方案。新增 message 级事件树 + `fork(from_message_id)`，fork 出的会话继承历史但写入独立文件。
  验收：`tests/test_session_fork.py`——10 条消息的会话在第 5 条 fork，断言两个会话文件独立、fork 出的会话追加消息不影响原会话、CLI `--resume` 能列出并恢复 fork。

- **M8-T3 插件 API 稳定化** — `minicc/tools/registry.py:register`、`minicc/tools/schemas.py`、新增 `docs/PLUGIN_API.md`、新增 `tests/test_plugin_api.py`
  改什么：`registry.register` 只在 `main.py:440` 与 `web.py:903` 被调用，无版本、无能力声明、无注册时校验。定义 ToolSpec 的稳定字段契约 + 版本号 + 注册期 schema 校验 + 冲突/覆盖语义（后注册者不得静默替换内置工具）。
  验收：注册一个带非法 schema 的插件被拒并给出可读错误；注册与内置同名的工具被拒（除非显式 `override=True`）；`docs/PLUGIN_API.md` 里的示例代码可原样跑通（文档测试）。

- **M8-T4 可安装产物** — `pyproject.toml`（package-data 含 `web/` 与 `ide/`、版本单源）、`scripts/build-web.mjs`、新增 `scripts/build-dist.ps1`、新增 `tests/test_packaging.py`、`README.md`、`docs/BENCHMARK_EVALUATION.md`
  改什么：无 wheel/sdist；`[tool.setuptools.packages.find] include=["minicc*"]` 不含 `web/`，真正 `pip install minicc` 会 404 工作台；README:192 的示例引用了 package.json 里不存在的脚本。纳入 web/ 构建产物；版本从 `importlib.metadata` 单源读取；提供 wheel/sdist 构建脚本与干净 venv 冒烟测试。
  验收：`pip wheel . -w dist` 后 `pip install dist/minicc-*.whl` 到干净 venv，`minicc --version` 与 `minicc-web --workspace . --port 8xxx` 均可用且 `index.html` 与 bundle 返回 200；版本号三处一致；README 的验证示例命令全部存在于 package.json。

- **M8-T5 可观测性：logging 取代 print 加 metrics 与错误上报** — `minicc/*`（55 处 print → logger，分批提交）、`minicc/webserver.py`（请求日志）、`minicc/web.py`（`/api/audit` 与新增 `/api/metrics`）、新增 `minicc/logging_setup.py`
  改什么：`minicc/` 零 logging 使用、55 个 `print()`，失败只表现为 inline 500 JSON。引入按模块的 logger + `MINICC_LOG_LEVEL` / `MINICC_LOG_FILE`，默认 WARNING 到 stderr 不污染 stdout 协议；把审计事件、provider 重试、预算事件、MCP spawn、hook 执行统一走结构化日志；`/api/audit` 增加按级别过滤；失败路径输出结构化 error code 而非裸 500 JSON。
  验收：`tests/test_logging.py`——设置 `MINICC_LOG_LEVEL=DEBUG` + `LOG_FILE` 后跑一个 fake provider 任务，断言日志文件含 `provider_retry`、`tool_round_finished`、`run_finished` 且不含 api_key 与 web token（用 grep 断言）；`/api/metrics` 返回的 token/成本与单任务快照对得上；`git grep -c 'print(' minicc/` 从 55 降到 ≤5（仅 CLI 交互输出）。

- **M8-T6 tests/test_core.py 拆分** — `tests/test_core.py` → `tests/test_core_{agent,tools,task,llm,session}.py`
  改什么：`test_core.py` 118KB / 109 个测试是单文件巨块，按 domain 拆开，避免 M4 新增 ≥60 条用例后得到一个无法导航的 170+ 函数文件。低风险、无行为变更。
  验收：pytest 收集数不变且全绿、CI 墙钟不升。

---

## 四、明确不做什么（以及为什么）

**结构性约束（贯穿 M1–M8）**：
- **不拆分 `minicc/web.py`（1885 行）与 `minicc/task_manager.py`（2276 行）**。这是典型的一个月重构、零用户可见收益，且这两个文件正是 M2/M3/M6/M7 全都要动刀的地方——先拆后改等于做两遍。只允许窄提取，白名单仅三项：`_resolve_workspace_path`（M2-T1）、MCP spawn 环境净化收口（M2-T7）、`should_allow` 审批通道（M7-T3）。

**尊重项目自身非目标（README「当前边界」+ `docs/AGENT_LLM_ROADMAP.md` §6）**：
- **向量库 / 语义检索**：不直接引入。改为 M4-T7 的可执行决策门——先产出 `recall@5` 基线，≥0.6 则明确写下「不引入」的结论并停止投入；<0.6 才允许本地 embedding（sentence-transformers 本地推理，不用外部向量库），且必须有 A/B 数据。
- **Redis / 分布式队列 / 跨机执行**：可靠性继续走 SQLite + 租约（M3-T5 的栅栏修复即是此路线）。
- **无约束递归多 Agent**：M6-T1 的可写委派保持深度上限 2、并发上限 3、显式预算、继承 `permission_mode`，且结构上排除 `task` 工具。
- **暴露模型私有 CoT**：任何 milestone 都不把 `reasoning_content` 写进 trace 或前端。
- **多用户身份 / RBAC / OAuth / 云端协作 / 限流**：M3 只把「单一 token 且无 Origin 校验」补成「单一 token + 强制 Origin 校验」，不引入账号体系。
- **完整 Monaco 编辑器 / 内嵌终端**：继续用文件预览加 diff 视图；「跑个 dev server」的诉求由 M6-T4 的后台 shell 覆盖。

**显式拒绝的一项路线图建议**：
- **拒绝放松「自动 git commit」非目标**。有路线图建议放松它以服务 A/B 实验固化（把每次实验固化为可回滚 commit），理由是成立的，但实现方式选错。采纳理由、拒绝做法：用现有的 bash 路径 + 一条文档化的「revertible commit」一行命令满足实验回溯，**不新增 typed git 工具**（git_commit/git_stage/git_push）——因为 typed git 写操作与「不自动提交」的边界极容易在实现中滑边，且它的可见价值低于 hooks 与 slash 命令。commit 永远由人触发。

**延后（带理由，不丢失）**：
- **输出风格 / persona**（S 级但纯装饰）：本质是一条 system prompt 片段，M7-T2 的 slash 命令/Skills 落地后即可实现，不单独立项。
- **IDE 集成深化**（现为 25 行两条命令）与 `ide/vscode/extension.js`：可见价值低于 M6–M8 任何一项，排在 M8 之后，等 `pip install minicc` 稳定后有真实用户反馈再投；README 降级标注为实验性。
- **多模型 per-stage 路由与跨厂商故障转移**：`router.py` 现在只缩放 timeout，但对单用户本地 agent 的可见价值接近零，而 M4-T4 的成本核算已经能暴露贵模型问题。
- **MCP sampling**：resources/prompts/健康检查在 M5-T7 落地，sampling 牵涉让远端 server 反向驱动本地 agent，安全模型未设计前不做。
- **CLI / 错误信息 / README 的英文 i18n**：团队语言是中文，翻译不改变能力。
- **删除街机小游戏需所有者批准**：`web/src/game.js`（1562 行）+ `web/src/core/arcade.js` + `tests/game_upgrade_smoke.mjs`（258 行）+ `package.json` 的 `test:game`/`test:all` + CI 的 `node --check`。本路线图建议删除（与 coding agent 目标零相关却常年消耗构建、smoke 与 review 面积）；若所有者不同意，则改为移出主 bundle 与 CI 并停止维护。

---

## 五、要删除/清理的东西

**M4-T9（评测可信度 milestone 内完成，避免"只做加法的路线图"）**：
- 仓库根一次性 repro 产物：`repro_budget.py`、`repro_id_collision.py`、`prev_test.txt`、`testlist.txt`、`pytest_full.log`、`pytest_full.err`、`pytest_verify.log`、`.tmp_audit_repro/`
- `web/assets/` 下 20 个陈旧内容 hash bundle 与未引用的陈旧 CSS，只保留 `asset-manifest.json` 引用的 1 份，并加 CI freshness 检查
- 被 gitignore 且无人引用的 `web/app.min.js`
- CI 中完全孤立、引用不存在文件的 `tests/codex_smoke.mjs`

**M1-T3（代码重复）**：
- `minicc/agent/loop.py:191-207` 的 `_merge_incremental_text`——`minicc/llm/stream_merge.py` 抽出后删除这第二份逐字拷贝

**M4-T9 + M8-T6（文档与版本）**：
- 版本号四处不一致（pyproject 0.1.0 / `main.py` 硬编码 / MCP `clientInfo` 0.2.0）统一到 `minicc/__init__.py.__version__`
- `docs/BENCHMARK_EVALUATION.md:46` 的「23 项通过」改为由脚本生成
- `README:192` 引用的不存在的 `npm run typecheck` 改为 package.json 真实脚本
- `docs/` 15 份中三份大量重叠（`OPTIMIZATION_DELIVERY_2026-09-18`、`DEEP_OPTIMIZATION_PLAN`、`PROJECT_REVIEW_2026-09-18`）合并，收敛到 ≤11 份，且无两份文档陈述同一组数字

**需所有者批准**：
- 街机小游戏三件套 + 其 CI/smoke 接线（见第四节末）

**明确不删（已核验为活代码，任何删除清单都不得包含）**：`web/app.js`（`scripts/build-web.mjs` 从 `web/src/main.js` esbuild 出的产物，`asset-manifest.json` 指向，`static_assets.py` 服务）、`web/index.html`（入口 HTML）、`web/src/core/i18n.js`（被 8 个模块 import）、`scripts/build-web.mjs`（CI 的 `npm run check:web` 依赖）。

---

## 六、每个阶段应该跟踪的指标

| 指标 | 定义 / 命令 | 目标 | 归属 |
| --- | --- | --- | --- |
| **质量** | | | |
| false_completion_rate | 把 failed / incomplete / max_tokens / refusal / 缺 finish_reason 五类非终态回合算成 completed 的比例 | 恒 0，任何回归必须红灯（CI 命名指标） | M1 建立，M4 起 CI 门禁 |
| pass@1 | `--suite v2 --repeat N`，N≥3 给 Wilson 95% CI，N<10 不下结论 | 分母 ≥24（edit ≥10），grading_coverage 恒 1.0 才允许对外引用 | M4 |
| verification_cache_false_positive | 改 `.md/.sh/Makefile`/无后缀文件后仍复用旧「通过」缓存的次数 | 恒 0，一条专门断言 | M4 |
| 证据门诚实度 | bash 造成的写入触发 `verification_required` 的比例 | 100% | M4 |
| recall@1 / recall@5 / MRR | `--suite retrieval` | 建基线；recall@5 ≥0.6 则明确不引入向量检索 | M4 决策门 |
| **效率** | | | |
| latency_p50_ms / latency_p95_ms | 端到端，按 category 分解 | 基线 P50 115s / P95 826s 写入 `docs/BENCHMARK_EVALUATION.md`；M6 起作为回归门 | M4 基线，M6+ 门禁 |
| llm_turn_p95_ms | 单次 provider 请求 | 随 M5 MCP P99 一并跟踪 | M4 |
| turns_per_success / tool_repeat_rate | 停滞检测与压缩是否真在省 token | 不升（A/B 判据） | M4 起 |
| fan-out 回归护栏 | token/task 与 P95 相对 M4 基线 | 劣化 ≤15%，否则回退 fan-out 阈值 | M6 |
| 委派率 / 平均并行子代理数 | 含 task 工具调用的任务占比 | M6 后从 0 起步，深度恒 ≤2、并发恒 ≤3 | M6 |
| **成本** | | | |
| cost_per_success_usd / tokens_per_success | 含失败尝试摊销；未知模型显式 None 不估算 | `cost_available` 恒 100% | M4 |
| Anthropic prompt cache 命中率 | M1 修好 `usage.py` 归一化后才可作真实指标 | 稳定 >0.30（验证 M1 修复没被后续重构打破的最便宜哨兵，挂 M4 CI 门） | M1 修，M4 门禁 |
| $/task 与 token/task | 每次 benchmark 报告 | 作为 M6 fan-out 的回归护栏 | M4 |
| **可靠性** | | | |
| 挂死计数 | 30 条 fixture 全量跑，无用户取消却超单任务墙上时钟上限（1800s）的任务数 | 0 | M1 |
| 流式保真度 | golden delta 序列（空行/缩进/重复 token/JSON 分片）逐字节往返相等 | 100% | M1 |
| 单轮请求次数 | 缺 finish_reason 的网关下每轮 HTTP 请求数 | ≤1（此前默认 5 次） | M1 |
| MCP 健壮性 | 工具输出 ≤6000 字符的比例；单次调用 P99 | 100%；P99 <5s（此前中毒后恒 30s） | M5 |
| CI 墙钟 / flake 率 | PR 评测门 | ≤15 分钟，真实模型只进 nightly | M4 |
| **安全** | | | |
| 越权尝试 | workspace_roots 外提交、plan 模式 exec 节点、junction 枚举、allowlist 自举、读 web_token.json 五类 | 全部被拒，≥12 条先红后绿回归 | M2 |
| 网络逃逸 | pip3 install / 双空格 git clone / rsync 等在 `allow_network=False` 时 | 全部拦截（≥20 条表驱动） | M3 |
| SSRF | rebinding 场景（守卫开启、不设 `MINICC_ALLOW_PRIVATE_FETCH`） | 拒绝连接 | M3 |
| 凭据泄漏面 | `.minicc/`、`web-*.stdout.log`、`.minicc/worker/*.config.json` 中 `sk-` 与 bearer 明文命中数 | 0 | M3 |
| 审批覆盖率 | default 模式下有显式决策事件的写/exec 调用占比 | 100%，记录审批中位时延 | M7 |
| **上下文** | | | |
| HTTP 面覆盖率 | POST `/api/*` 路由有 Python 测试的比例 | 100%（此前 0%） | M4 |
| CI 真实性 | `MINICC_BASE_URL` 指向不可达地址时 `npm run test:web` 退出码 | 非 0（写成断言而非「接入 CI」） | M4 |
| 证据可引用性 | 100 个 write 事件 + 5 个 trace 的会话里 event-1 仍可被引用；零工具调用的只读任务无法只用 trace id 判 complete | 两条都必须成立 | M4 |
| 记忆索引注入规模 | 系统提示注入的记忆条数上限 | ≤50 条且标注省略 | M8 |
| 可观测性 | `minicc/` 下 `print()` 数量 | 从 55 降到 ≤5（仅 CLI 交互输出），日志不含 api_key | M8 |
| installability | 干净 venv `pip install` 后两个 entry point + UI 200 | 通过 | M8 |

---

## 七、面试讲解要点：这个路线图本身能讲出什么工程判断

1. **「引擎好」不等于「产品好」，更不等于「可信」。** 这个项目的 ReAct 循环、压缩、协议校验、DAG 调度都是真实设计，但 `openai_provider.py:878` 一个把「重试 attempt 全文对齐」的合并逻辑误用到每个增量 delta 上的缺陷，就能让 `write_file` 的参数变成内容错误的合法 JSON。讲解要点：**正确性缺陷的价值不在严重度标签，而在它污染的下游有多大**——同一个 delta 会被子代理回放、被 hooks 改写、被检索喂回去。所以 M1 修的是管道不是症状。

2. **排序的本质是「给执行体加杠杆之前先拆掉杠杆的支点」。** 可写子代理、hooks、后台 shell 都是放大器。在 `allowlist.py:165` 的 `fnmatch(name,"*")` 还能被 agent 自己写文件触发、`workspace_roots` 只在 `switch_workspace` 一处生效、`bash.py:106` 对 `argv[0]==pytest` 直接放行的前提下开放并行写，等于把「一条命令自我提权」复制成「每条并行分支都能提权」。这是本路线图与另两条候选路线的根本分歧：**能力对齐优先把可写子代理放在权限封闭之前 3.5 周，是唯一一处会主动放大攻击面的排序错误**。

3. **会挂死的缺陷优先级高于会泄密的缺陷，判断依据是「是否必经之路」。** `loop.py:1263` 的死循环之所以是 P0，不是因为 bug 更深，而是因为 `web.py:1450` 传 `require_recovery_inspection=(agent_recoveries > 0 or repair_attempts > 0)`——每次 repair、每次恢复后都可能触发。**一个缺陷是必经之路还是边缘路径，决定了它该排在第一个还是最后一个。**

4. **验收标准必须可证伪，否则就是恒绿断言。** M2 的 ≥12 条安全回归全部要求「先红后绿」——在未修复代码上必须失败。同理，`npm run test:web` 只断言「loading 元素出现」所以 provider 指向不可达地址时仍打印 passed；把它改成「不可达必须非 0 退出」才是门禁。**一条测不出故障的测试，比没有测试更危险，因为它制造了虚假信心。**

5. **测量优先的前提是测量工具本身没被污染。** 这是评测驱动路线图最有价值也最自相矛盾的地方：它要产出 `false_completion_rate`，却把「失败回合归一成 stop」推到 M4、把「bash 写入绕过验证门」推到 M3——于是头号指标建立在一个会说谎的判定器上。本路线图因此把证据链修复（M4-T1）放在产出任何 benchmark 数字之前，并给 A/B 对比器配 Wilson 95% CI 和「CI 用构造数据验红」。

6. **非目标要写成决策门，而不是散文。** 「不引入向量库」如果只写在 README 里，就永远无法证伪。改成 M4-T7：先出 `recall@5` 基线，≥0.6 就明确写下不做的结论并停止投入。<0.6 才允许施工。**把判断变成数据，路线图才不需要靠权威维持。**

7. **诚实标注工作量，是对兼职节奏唯一的尊重。** 原方案 21 周装 6 个 milestone，其中 M1 3.5 周要装 7 个任务（含新模块、30 条新用例、探针脚本、双平台 CI）。真实节奏是系统性乐观 30–40%。本路线图 36 周 ≈ 8 个月，并预先给出滑出 9 个月时的砍单顺序（记忆 → fork → Skills → 写并行，前四个 milestone 一刀不砍）。**会说「做不完砍什么」的路线图，比说「21 周搞定」的路线图更可执行。**

8. **拒绝两个诱惑，本身就是要讲出的判断。** 一是拒绝拆分 `web.py` / `task_manager.py`：这两个文件正是 M2/M3/M6/M7 全都要动刀的地方，先拆后改等于做两遍，一个月零用户可见收益。二是拒绝为 A/B 回溯而放松「不自动 git commit」：它的理由成立（实验需要可回滚固化），但实现选错——用现有 bash 路径加一条文档化的一行命令即可，新增 typed git 工具会让「模型只提案、提交永远由人触发」这条边界在实现中滑边。**正确的路线图不只写做什么，更要写清拒绝什么以及为什么。**

9. **删除清单的可信度等于整份路线图的可信度。** 一份只做加法的路线图不可信。但删除必须逐条核验：本路线图删的是真死物（20 个陈旧 bundle、1562 行彩蛋、根目录 repro 产物、loop.py 重复合并拷贝、孤立的 codex_smoke.mjs），并明确列出「已核验为活代码、任何删除清单不得包含」的四个文件——某候选路线图正因为把 `web/app.js` / `web/index.html` / `web/src/core/i18n.js` / `scripts/build-web.mjs` 当死代码删，会一次性摧毁整个 Web 产品与 CI。**分不清死代码和活代码的清理计划，破坏力比不清洗更大。**

---

## 附录 A：完整性批判指出的漏项与归属

以下由独立的完整性批判 agent 提出，经复核成立。**执行前必须把这些补进对应里程碑，否则路线图自己的验收标准会被架空。**

### A.1 已确认缺陷漏项

| 漏项 | 位置 | 为什么必须补 | 归属 |
| --- | --- | --- | --- |
| config.py 剩余 6 个缺陷 | `config.py:165`（非对象→AttributeError）、`:179`（丢 0/false）、`:183`（列表变 repr）、`:94`（行内注释/export）、`:77`（home_dir mkdir）、`:145`（describe 打 key） | 其中 **`:183` 直接架空 M2-T1**：M2 的 workspace_roots 四入口白名单建立在 `config.py:259-265` 正确解析 roots 之上，用户按 `minicc.config.example` 写 JSON 数组时 M2 会静默退化。**:94` 直接架空 M2-T8`：让 `.env` 生效后，`MINICC_MODEL=x # note` 仍会把注释发给网关、`MINICC_YOLO=1 # on` 仍变 False。**:145` 与 M3"`grep -rn sk-` 无命中"退出标准同类 | M7-T4（提前 `:183`/`:94` 到 M2-T8） |
| `read_file` 对 offset/limit 仍整文件读 3 次 | `editor.py:305-312`、`fs.py:88-92` | M2-T6 只补了 grep 的大小上限 | M2-T6 |
| CI 卫生 5 项 | `ci.yml`、`pyproject.toml:24`、`README.md:192`、版本号三处、`web/assets/` 21 个死 bundle | M4-T8 文本被截断，`httpx` 传递依赖（一次 openai 升级即双平台 CI 全红）与版本号统一实际未覆盖 | M4-T8（明确列出）+ M8-T4 |

### A.2 高价值能力差距漏项

| 漏项 | 位置 | 归属建议 |
| --- | --- | --- |
| **模型 per-stage 路由与跨厂商故障转移** | `router.py`（只缩放 timeout，明确拒绝覆盖模型）；fallback 是单一全局列表 | 与 M4-T4（美元核算）和 M6（fan-out 成本护栏）强耦合 → **M6-T6 新增**：per-stage 模型档位（fast/balanced/reasoning）+ 成本上限 + 跨厂商 failover |
| **i18n / a11y 已确认未修缺陷** | `docs/PROJECT_REVIEW_2026-09-18.md:83-85,153`：纯图标按钮在无障碍树无可用名称、暗色对比度不足、移动端发送按钮裁切 | **M7-T6 新增**：a11y 修复（aria-label / tooltip / 键盘焦点 / 对比度 ≥4.5:1 / 触控区域）。注：联网开关 `display:none` 一条已修复，不在内 |
| **typed Git 写操作的边界声明** | `tools/git.py` 全只读 | 必须显式声明与 README 非目标"自动 git commit"的边界，否则实现中会滑边。建议：只做 `git_stage` / `git_commit`（**永远由人触发**，agent 只能提案），不做 push/PR |
| **@-提及不注入文件内容** | `web/app.js` 的 `applyMentionOption()` | 已并入 M7-T5 |
| **MCP resources/prompts/sampling 与健康检查** | `mcp.py` | resources/prompts/健康检查并入 M5-T7；**sampling 显式延后**（让远端 server 反向驱动本地 agent，安全模型未设计前不做） |
| **消息级事件树** | `session.py` | M8-T2 的 fork 隐式依赖它却未写 → **M8-T2 明确先建事件树再 fork** |
| **输出风格 / persona** | `prompt.py` | 不单独立项。M7-T2 的 slash 命令/Skills 落地后即可实现（本质是一条 system prompt 片段） |
| **IDE 集成深化** | `ide/vscode/extension.js` | 延后到 M8 之后，README 降级标注为实验性 |
| **多用户 RBAC / 限流** | `webauth.py` | 属 README 已声明非目标 → **在第四节显式记为非目标**，避免静默缺失读起来像遗漏 |

### A.3 会重造或撞车已有实现的步骤（执行前必读）

1. **M4-T4（价格表）部分重造**：`benchmarks.py:103,117,134,140,164` 已有 `cost_usd` / `cost_per_success_usd` / `cost_available` / `total_cost_known` 的完整聚合，`grading_coverage` 与 `pass_at_1` 也已存在。真正缺的只有**单价表和 usage 侧填值**。应在 `add_usage_totals` / `state.py` 侧产出，benchmarks 只读，**不要再造一套聚合**。
2. **M1-T3 与既有测试有隐性冲突**：`tests/test_core.py:35` 直接 import `_merge_stream_text`，`:1510` 断言 `_merge_stream_text("aa","aab") == ("aab","b")`——**这条测试固化的正是缺陷语义**。因此 M1-T3 必须落成**两个函数**（delta 逐字节拼接 + attempt 全文合并），否则要么打破"既有测试不得回归"，要么把缺陷留下。验收里的"先红后绿"需写明边界。
3. **M2-T5 + M3-T4 会造出第三、四套命令解析**：`bash.py:88` 已有 `.split()` 版 `is_readonly_command`、`:60` 有 regex 版 `detached_command_reason`、`audit.py:88` 是子串版。M3-T4 若再在 audit.py 里写 argv 分词就是第三份并存 tokenizer。**应先抽一个共享 argv tokenizer（shlex + Windows 兼容）供 audit.py / bash.py 共用。**
4. **M2-T1 的提取层次**：`web.py:383-394` 已内联整套 resolve + `is_relative_to` 校验，`config.py:259-265` 已在解析 roots。`_resolve_workspace_path()` 应放在 **config/workspaces 层**而非 web 层，否则四个入口仍要 import web。
5. **M5 的"零测试"表述要收敛到 stdio**：`tests/test_mcp_http.py` 已有 8 个 HTTP 测试。真正零测试的是 `McpStdioClient`（`mcp.py:101`）。否则会重复造 HTTP 侧用例。
6. **M6 后台 shell 不应新写进程管理**：`bash.py:118-135,189-266` 已有 `run_process(cancel_event)` / `terminate_process_tree` / `_process_group_kwargs`，`sandbox.py` 已有 `SandboxRunner`。应**扩展而非并行实现**。
7. **M8 记忆若另建存储会出第二份持久化层**：`session.py` / `task_store.py` 已有 SQLite schema 与关键词搜索，`retrieval.py` 已有确定性打分。复用点必须写清。
8. **正例（已是正确做法，保持）**：M4-T7 的 `--suite` 机制已存在（`benchmarks.py:176` 的 `choices=("legacy","behavior")`），扩 choices 即可；M4-T5 对"fixture 隔离已存在"的自我修正经核实成立。

---

## 附录 B：主审核人核验注记

本路线图由 4 个独立方案 + 3 个评委 + 1 个综合 agent 产出后，由主审核人对关键声明逐行复核。以下是与工作流产出的原文之间的**差异**，以本节为准：

1. **P0 排序调整**：`openai_provider.py:878` 的流式增量重叠合并从"HIGH"提升为**与死循环并列的 P0**，并且是三者中唯一会**静默损坏数据**的一个。已用项目自身函数实测复现（`'hel'+'lo' → 'helo'`；工具参数 `"hello world"` → `"helo world"`），并确认 388 个全绿测试只因唯一相关测试只覆盖了累积快照分支。详见 [AUDIT_2026-09-20.md](AUDIT_2026-09-20.md) P0-1。
2. **M1-T4 的机制修正**：原文写"`:785` 把 `response.failed` 归一成 `finish_reason='stop'`"。逐行复核后修正——`:785` 实际是 `"stop" if status == "completed" else status`，**并未归一**；真正的问题是 `minicc/agent/loop.py` 全文零次读取 `finish_reason`。修复点在 loop 侧（显式拒绝非终态回合），provider 侧只需保证 `failed`/`incomplete`/`max_tokens`/`refusal` 不被误报为 `stop`（注意 `:990` 的 `or "stop"` 确实会把缺失值归一）。
3. **M2-T2 的同类项已扩充**：除 `allowlist.json` 外，`web_token.json` / `mcp.json` / `todos.json` 都应纳入敏感路径集合（读脱敏、写拒绝），并按完整路径后缀匹配而非仅文件名。
4. **M2-T5 增加 `READONLY_PLAN_KINDS` 修正**：除 `node_allow` 传 `permission_mode` 与 pytest argv 白名单外，还应把 `"exec"` 移出 `task_manager.py:69-70` 的 `READONLY_PLAN_KINDS`，或禁止只读 DAG 节点声明 bash。
5. **M3-T5 的修复是一行**：`UPDATE task_leases SET ... WHERE task_id=? AND owner=? AND expires > ?`（绑定 `now`）。已在代码中确认 `claim_lease` 有该栅栏而 `heartbeat_lease` 没有。
6. **M4-T2 的验收要写成断言而非"接入 CI"**：把 `MINICC_BASE_URL` 指向不可达地址时 `npm run test:web` 的退出码必须非 0——这是一条能在 CI 里抓住"任务链路整体坏了"的网，也是整个 M4 里最便宜的一条。
7. **第五节删除清单的边界**：`web/app.js`、`web/index.html`、`web/src/core/i18n.js`、`scripts/build-web.mjs` **已核验为活代码，任何删除清单不得包含**。某候选路线图因把这四个当死代码删，会一次性摧毁整个 Web 产品与 CI。
8. **第六节指标新增两条**：
   - `false_completion_rate`：把 `failed` / `incomplete` / `max_tokens` / `refusal` / 缺 finish_reason 五类非终态回合算成 completed 的比例，**恒 0，任何回归必须红灯**（M1 建立，M4 起 CI 门禁）。
   - `证据门诚实度`：bash 造成的写入触发 `verification_required` 的比例，目标 100%（M4）。
9. **第九节「删除街机小游戏需所有者批准」**：本路线图建议删除（`web/src/game.js` 1562 行 + `web/src/core/arcade.js` + `tests/game_upgrade_smoke.mjs` 258 行 + `package.json` 的 `test:game`/`test:all` + CI 的 `node --check`），或退而求其次移出主 bundle 与 CI 并停止维护。**需项目所有者决定。**

---

## 附录 C：方案比选记录（路线图选型依据）

本路线图由 4 个独立战略角度的候选方案 + 3 个评委按 5 项标准打分后综合而成。保留本节是为了让「为什么选这条路而不是那条」可复查。

### C.1 四个候选方案的核心论点

| 方案 | 核心论点 | 强项 | 被评委扣分的点 |
| --- | --- | --- | --- |
| **可靠性优先**（优胜，均值 41/50） | 先让「模型→工具→结果」这条管道会终止、不静默损坏数据，再谈任何能力扩张 | 把 100% 能力扩张压到第 12 周之后；识别出 hooks/子代理/后台 shell 会把现有单点缺陷复制成多点；工期估计最保守 | 前 12 周「没有新功能」对面试展示不友好 |
| **能力对齐优先**（39/50） | 直接对标 Claude Code 的能力清单（可写子代理、hooks、slash 命令） | 产品形态最快接近目标；任务清单最完整 | 在 allowlist 自我提权与流式静默损坏未修前引入可写委派，等于把「一条命令自我提权」变成「每条并行分支都能提权」 |
| **评测驱动爬坡**（31/50） | 先把「行不行」变成可度量事实（pass@1 分母、CI 门、A/B 门），用度量牵引后续排序 | 唯一一个把「不可证伪」当第一问题的方案；成本指标设计最完整 | 假设「评测数据会告诉我们要做什么」——但 pass@1 分母只有 3、`cost_per_success_usd` 恒 None，度量本身依赖先修 provider 层 |
| 第四个候选（未获高分） | 以 Web 产品化 / 前端体验为轴心推进 | 用户体验路径最清晰 | 与 README 已声明的非目标（多用户、云端协作）冲突，且忽视后端地基缺陷 |

### C.2 评审的 5 项标准

假设正确性 / 排序合理性 / 工期现实性 / 是否达成目标 / 是否尊重非目标。

### C.3 从次优方案嫁接的想法

- 来自**能力对齐优先**：M6（有界可写委派 + 后台 shell）、M7（Hooks / slash 命令 / 交互审批 / 项目配置）、M8（记忆 / fork / 插件 API / 可安装产物）。这三个里程碑整体保留，只是**排在 M1–M5 之后**。
- 来自**评测驱动爬坡**：M4 整章的「证据链与评测可信度」（价格表、A/B 门、`false_completion_rate` 恒 0、`grading_coverage` 恒 1.0 才允许对外引用）。这是把优胜方案「先修地基」的判据从主观变成可拦截的 CI 门。
- 来自**评委对优胜方案的批评**：36 周而非 21 周；把 `latency_p50/p95` 基线（P50 115s / P95 826s）写进第六节，让「能力扩张是否拖慢」可判定。

### C.4 评委指出的致命缺陷（已写入正文对应位置）

1. **删除清单误杀活代码**：某候选方案把 `web/app.js`、`web/index.html`、`web/src/core/i18n.js`、`scripts/build-web.mjs` 当死代码删除——会一次性摧毁整个 Web 产品与 CI。已改为第五节末的「明确不删」硬约束。
2. **工期系统性乐观 30–40%**：把 7 个任务的 M1 估成 3.5 周。已改为 4.5 周并把总工期定为 36 周。
3. **只做加法的路线图**：没有删除清单。已补第五节（含 M4-T9 与明确的「需所有者批准」项）。
4. **能力前置于地基**：在 P0 未修时引入 hooks / 可写子代理 / 后台 shell。已用「M1–M5 一刀不砍、能力扩张全部 ≥M6」的依赖关系锁死。

---

## 附录 D：实施进度日志（2026-09-20 起）

本节记录路线图任务的**实际落地状态**，与上文计划分开维护。

### 已完成（M1 核心链路可信）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M1-T1 恢复阶段死循环 | ✅ | `loop.py` 新增 `recovery_refusals` 计数器（`:398` 定义、`:1266` 自增、`:1270` 判限、取得只读证据时 `:1046` 清零） | `tests/test_m1_integrity.py::test_m1t1_recovery_required_does_not_loop_on_plain_text`（`calls <= 5` + `recovery_guard`） |
| M1-T2 非流式 tool_call id 复用 | ✅ | 新增 `_unique_tool_call_id()`（`openai_provider.py:261`），应用于 `_assembled_tool_calls` / `_to_response` / `_responses_to_response` 三处，各自独立 `seen_ids` | `test_m1t2_tool_call_ids_deduplicated` |
| M1-T3 流式增量吞字符 | ✅ | 新增 `minicc/llm/stream_merge.py`：`append_delta`（纯拼接）/ `accumulate_attempt_text`（前缀识别累积快照）/ `merge_retry_snapshot`（仅重试对齐）。`_create_stream` 的 delta 与 tool 参数分片改为纯拼接；`loop.emit_stream` 改用 `accumulate_attempt_text` | `test_m1t3_incremental_deltas_concatenated_byte_for_byte`；`_merge_stream_text` 保留为兼容 shim |
| M1-T4 失败/截断伪装成功 | ✅ | `llm/base.py` 新增 `TERMINAL_FINISH_REASONS` / `NonTerminalModelTurn`；`loop.py:1261` 新增独立 `nonterminal_repairs` 计数器守护；Anthropic 的 `stop_reason` 不再被归一为 `stop` | `test_m1t4_nonterminal_finish_reason_never_accepted`、`…_persistent_nonterminal_fails` |
| M1-T5 缺 finish_reason 整段重放 | ✅ | 新增 `StreamProtocolError`（`openai_provider.py:166`），`_is_stream_retryable` 对它返回 False；`"stream ended before completion"` 从可重试子串列表移除 | `test_m1t5_stream_without_finish_reason_fails_fast`（断言只发 1 次请求） |
| M1-T6 缓存记账 | ✅ | Anthropic 新增 `_normalize_usage()`：`prompt = input + cache_read + cache_write`、`miss = input`（不再 `prompt - hit`）；`_sse_to_llm` 与 `response_to_llm` 共用；`_parse_usage` 的 cache 计数强制 `int` | `tests/test_anthropic_provider.py::test_response_maps_usage_and_tool_use` 已更新为 192/212/100 |
| M1-T7 envelope id 与降级丢 tool_calls | ✅ | `envelope.py` 改用进程内单调计数 `_next_envelope_id()`；新增 `_render_envelope_action()`；`_to_envelope_wire` 的 assistant tool_calls 不再折叠为空 content | `test_m1t6_and_t7_envelope_roundtrip` |
| M1-T4 附带：Anthropic max_tokens | ✅ | `DEFAULT_MAX_TOKENS` / `MAX_TOKENS_HARD_CAP` + `_clamp_max_tokens()`（支持 `MINICC_ANTHROPIC_MAX_TOKENS`），替换硬编码 `8192` | 由 `_clamp_max_tokens` 单测覆盖（见 `test_anthropic_provider.py`） |
| M1-T8 可靠性探针与 CI job | ✅ | 新增 `scripts/reliability_probe.py`：用 pytest 节点 ID 精确复现 M1-T1..T7 全部缺陷，退出码 0；`.github/workflows/ci.yml` 新增独立 `reliability-probe` job（任一 M1 回归即红）；删除仓库根目录一次性复现产物 `.t1.log`/`.t1.err`/`.t2.log`/`.t2.err` | `python scripts/reliability_probe.py` 退出码 0（12 用例通过） |

### 已完成（M2 权限模型与工作区边界，部分）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M2-T1 workspace_roots 单点生效 | ✅ | 新增 `workspaces.resolve_workspace_path()`（roots + 存在性 + 解析统一门），四个入口全部接入：`web.switch_workspace`、`web._rpc_workspace_path`、`web._run_chat`、`task_manager._workspace_path` | `pytest -rn` 显示原 `workspace_roots` 仅 1 处 enforcement，现 4 处共用同一函数 |
| M2-T2 `.minicc` 认证/授权文件 | ✅ | `tools/fs.py` 新增 `SENSITIVE_MINICC_FILES` + `_minicc_sensitive_kind()`；`allowlist.json` / `web_token.json` / `audit.jsonl` / `worker/*.config.json` 读写双拒；`mcp.json` 可读但 `_redact_mcp_headers()` 脱敏 headers | `test_m2t2_minicc_auth_files_are_not_agent_writable` |
| M2-T3 CLI allow 工具级通配 | ✅ | `main.py` 的 `a`（always）不再写 `tool=<name>`，只记录**具体命令/路径**；无具体参数时明确不写并提示 | 由 `main._permission_gate` 行为覆盖 |
| M2-T4 allowlist 明文与竞态 | ✅ | `allowlist.py`：写前 `redact_text`、读改写在 `RLock` 内、temp 文件名带 pid+uuid；新增 `_escape_brackets()` 让 `[REDACTED:…]` 能被 `fnmatch` 字面匹配 | `test_m2t4_allowlist_redacts_and_matches_redacted_command` |
| M2-T5 pytest `-p` 任意代码执行 | ✅（部分） | `bash.py::is_readonly_command` 重写为索引式 argv 白名单：`-p<module>` / `-c` / `--rootdir` / `--basetemp` / `--junitxml` / 绝对路径 / `..` / 未知 flag 全部拒绝；`-p no:<plugin>`（CI 关闭插件）仍放行；`READONLY_PLAN_KINDS` 移除 `"exec"`、`READONLY_PLAN_TOOLS` 移除 `"bash"`；`web.node_allow` 传入 `permission_mode` | `test_m2t5_pytest_readonly_gate_denies_dangerous_forms` |
| M2-T6 junction / 符号链接越界 | ✅ | `tools/fs.py` 清理 grep 死代码并给 grep 输出加大小上限；`read_file` 的 offset/limit 不再整文件三读（`editor.py` / `fs.py`）；junction/符号链接解析统一走 workspace 边界门 | `tests/` junction 回归用例（M2-T6） |
| M2-T7 MCP spawn 门控 | ✅ | 验证 `mcp.py` spawn 环境净化与门控已落地并接入 `audit.py`；补齐回归测试，确认无新增缺陷 | M2-T7 回归用例 |
| M2-T8 config.py 配置劫持与 .env 失效 | ✅ | `config.py:183` 列表不再被 `repr()` 字符串化（直接架空 M2-T1 的 roots 解析已修复）；`:94` `.env` 支持行内注释与 `export` 前缀，`MINICC_MODEL=x # note` / `MINICC_YOLO=1 # on` 现在正确解析 | config 回归用例（M2-T8） |

**M2-T5 的剩余部分**：已在 M3-T4 收口——`audit.py` 的网络门改为共用 argv tokenizer（`split_command_argv`），不再与 `bash.py` 各持一份分词逻辑（见下 M3 表）。

### 已完成（M3 凭据 / 网络 / 进程面）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M3-T1 do_POST Origin/CSRF 校验 | ✅ | `webserver.py::do_POST` 先按 `MAX_BODY_BYTES` 排空请求体再做 Origin 校验（修复 Windows 上未读体即关连接导致的 `ConnectionAbortedError`/WSAECONNABORTED），随后才鉴权 | `tests/test_web_security.py`（17 通过，含 `test_cross_origin_state_change_rejected_before_any_work`） |
| M3-T2 日志 token 脱敏 + Origin 403 HTTP 级 | ✅ | `webauth.py` / `audit.py` 对 SSE/web token 脱敏；CORS 回环判定收紧 | `tests/test_web_security.py` Origin 403 HTTP 级用例 |
| M3-T3 SSRF 防护加 IP 钉扎 | ✅ | `netguard.py` 新增 `_resolve_and_validate` / `resolve_pinned_host`（解析一次、逐个地址校验私有/保留段）；`webfetch.py` 新增 `_PinnedHTTPConnection` / `_PinnedHTTPSConnection`（钉住已校验 IP，保留原 Host 头与 TLS SNI=`server_hostname=host`），每一跳重定向重新校验，防 DNS rebinding | `tests/test_webfetch.py`（13 通过，含 `test_pinning_dials_validated_ip_not_rebind_target`、`test_redirect_hop_to_loopback_denied_without_env`） |
| M3-T4 网络门控改 argv 感知 | ✅ | `audit.py` 网络门由子串黑名单改为共用 argv tokenizer（`split_command_argv`），与 `bash.py` 不再各持一份分词逻辑 | `tests/test_p0_p1_p2.py` 网络门用例 |
| M3-T5 heartbeat_lease 复活已过期租约 | ✅ | `task_store.py::heartbeat_lease` 加上 `expires > now` 栅栏（与 `claim_lease` 一致），过期租约不再被心跳复活 | `tests/` 租约栅栏用例 |
| M3-T6 detached worker 明文 api_key 不落盘 | ✅ | `task_manager.py` 通过 stdin 管道把 config（含 api_key）交给 worker（`_worker_command` 发 `--config-stdin`，移除 `_write_worker_config`），新增 `_sweep_stale_worker_configs` 清扫 `.minicc/worker/*.config.json` 残留；`_monitor_worker` 两条路径都复查租约；`task_worker.py` 新增 `_config_from_stdin` | `tests/test_p0_p1_p2.py::test_worker_command_keeps_api_key_out_of_argv` 等；`tests/test_task_worker.py`（无 `*.config.json` / `*.request.json` 残留） |
| M3-T7 SessionStore 并发写损坏 JSON | ✅ | `session.py::_write_payload_at` 改用 `tempfile.mkstemp` 每次唯一临时名 + `os.replace` 原子替换 + 跨进程文件锁（Windows `msvcrt.locking` / POSIX `fcntl.flock`），消除 WinError 32 与半成品文件 | `tests/test_session_concurrency.py`（3 通过：线程并发、进程并发、单写者） |
| M3-T8 _rpc_threads 无界增长 | ✅ | `web.py` 用 `OrderedDict` 实现有界插入序 LRU（上限 512，淘汰最旧），新增 `_validate_thread_id`（长度≤256、拒控制字符），非法 id → JSON-RPC `-32602`（经 `/api/rpc` 以 HTTP 200 体承载） | `tests/test_rpc_threads.py`（6 通过） |
| M3-T9 批量任务与快照写入缺陷 | ✅ | `task_manager.py`：`submit_batch` 把 `batch_messages`/`batch_shared_context`/`batch_orchestration_mode` 存入父任务 context，`resume()` 对 `task_kind=="batch"` 走 `_resume_batch`（经 `submit_batch` 重建而非压平成单任务）；附件只在父任务持久化一次、子任务引用父路径（`_skip_attachment_persist`/`_persisted_attachments`），`_load_attachment_payloads` 根放宽到 `.minicc/attachments`。`task_persistence.py::close()` 每个 flush 独立 try/except 并保留首个错误，单个失败不再拖垮其余终态写入 | `tests/test_task_persistence.py`（2 通过）、`tests/test_batch_resume.py`（2 通过）；回归 `test_auto_resume`/`test_snapshots`/`test_p0_p1_p2`/`test_subagent_task`（41 通过） |

**M3-T8 验收偏差说明**：路线图验收写"返回 400"，但 `_rpc_thread_*` 抛出的 `ValueError` 按 JSON-RPC 规范映射为 `-32602`（invalid params），由 `/api/rpc` 以 HTTP 200 体承载；测试断言 `-32602`（更贴合实际契约）。

### 已完成（M4 证据链与评测可信度，全部）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M4-T1 先修证据链 | ✅ | 四处修复：(1) `tool_policy.py` 新增 `command_may_modify_workspace` / `is_workspace_write` 与 `WRITE_TOOL_NAMES`，`loop.py` 三处写判定与 `web.py::on_tool` 的 `write` 标志改用 `is_workspace_write`，`sed -i` / `python patch.py` / 重定向 / `git checkout` 等 bash 改写现在会触发 `verification_required`；(2) `verification_plan.py` 指纹 suffixes 补 `.md/.sh/.ps1/.svg/.png` 等并把无扩展名文件（Makefile/Dockerfile）纳入扫描，改这些文件不再复用旧通过缓存；(3) `completion.py::_enforce_completion_evidence` 区分 `packet_ids`（防幻觉）与 `citable_ids`（write/verification/error/真实 tool），完成判定必须至少引用一条真实证据，零工具只读任务无法只用 trace id 判 complete；(4) `_evidence_packet` 改为"保留最早 40 条重要事件 + 最新若干"配额，100 个 write 事件下 `event-1` 仍可被引用（旧的优先排序只保留最新 write 会逐出最早证据）。附带：`web.py::emit_node_event` 把只读 DAG 节点的 `kind=="tool"` 事件并入主 `events`，否则 planner 只读计划在判定器眼里像零工具会话；`config.py::normalize_model_name` 空串值回退默认（与 `normalize_reasoning_effort` 一致），修复 resume 旧任务记录无 model 时崩溃；(5) 对齐退出标准 2「正常 fake provider 下断言含至少一次工具证据」——`minicc/llm/fake.py::FakeProvider` 首个 agent 轮发一次只读 `tree` 调用、判定轮用新增 `_select_citable_evidence`（按完整 marker 定位用户消息里的证据包，镜像 `_is_citable_evidence` 选可引用 id，避免误匹配含「执行证据」字样的系统提示词），`tests/test_benchmark_runner.py` 的本地 fake 同步改造并复用该选择器；`tests/test_task_worker.py::test_worker_survives_host_restart` 的 `started_file` 断言由 `["started"]` 改为 `["started","started"]`（两轮 agent 调用，仍能证明 worker 未被重启复制） | `tests/test_m4_evidence_chain.py`（4 条命名回归，先红后绿）；`tests/test_core.py` 全绿（含重写的 `test_agent_service_preflights_complex_tasks_with_a_safe_model_plan`——原 fake agent 从不调用工具、靠 trace id 判完成，正是本任务要消灭的缺陷语义，按 A.3-2 重写为真调用 `read_file`）；`tests/test_task_worker.py`（5 条）、`tests/test_benchmark_runner.py`（15 条）、`tests/test_auto_resume.py`、`tests/test_subagent_task.py`、`tests/test_permission_modes.py` 全绿；`scripts/reliability_probe.py` exit 0 |
| M4-T3 Web HTTP 面 + RPC 的 Python 测试 | ✅ | 新增 `tests/test_http_surface.py`（56 条），起真实 `ThreadingHTTPServer` + 真实 `AgentService`（fake provider，无网络）用 `urllib` 打真实请求，补齐此前 `grep api/tasks tests/*.py` 为 0 命中的空白：(1) 每个 POST `/api/*` 路由至少一条——`/api/tasks`(202+`_defer_schedule`)、`/api/tasks/batch`、`/api/tasks/{id}/cancel`+`/resume`(404)、`/api/chat`(200 含 `fake-provider-answer`)、`/api/workspace/select`、`/api/allowlist`、`/api/sessions/rewind`、`/api/workspace/restore`、`/api/worktrees`+`/remove`(git init，201/200)、未知路由 404；(2) 传输层状态码——畸形 JSON 400、空体 400、`WebAuth(required=True)` 缺 token 401→带 Bearer 202、跨站 `Origin` 状态变更 403；(3) `workspace_roots` 白名单在 task/batch/select/chat/rpc.turn-start 五个入口越界均 400（rpc 为 HTTP 200 + body error code -32602）且含「白名单」；(4) 8 线程并发 submit 全 202 且 task_id 唯一；(5) `rpc.py` 分发器 ≥10 个 method 独立单测（参数化 m0..m9）+ initialize/未知 method(-32601)/非法请求/缺 jsonrpc 版本/method 类型/id 类型/params 非对象/通知返回 None/通知错误抑制/ValueError(-32602)/KeyError(-32004)/通用异常(-32000)/非 Mapping 返回/batch/空 batch/`parse_request` strip；(6) `/api/rpc` HTTP 集成——initialize+thread 往返、turn 生命周期(start→read→interrupt)、未知 method 与缺 task、非对象 body 400、通知 204。**测试自身缺陷修正**：`workspace_select` 返回 posix 路径，断言改用 `Path(...)==Path(...).resolve()` 归一化 Windows 斜杠；`rewind` 的 `keep_messages` 须 ≥1（0 触发 `SessionError`），断言改查响应 `kept` 键（rewind 不回显 session_id）。为把 56 条压进 20s，`serve_forever` 用 `poll_interval=0.05`（默认 0.5s，每个 server 关停各等一个轮询周期，~30 个短命 server 累计 ~13s） | `pytest tests/test_http_surface.py -q` 56 passed in 8.20s（< 20s） |
| M4-T4 价格表与美元成本核算 | ✅ | 新增 `minicc/pricing.py`：`ModelPrice`（USD/1M tokens 的 input/output/cache_read/cache_write 四价）、`DEFAULT_PRICE_TABLE`（仅收录公开标价的 gpt-4o/4o-mini/4.1/o1/o3、claude-3-5/3-7-sonnet、3-5-haiku、opus-4；虚构默认模型 `gpt-5.6-terra` **故意不收录**）、`price_for`（大小写不敏感**最长前缀**匹配，`gpt-4o-mini` 不会被 `gpt-4o` 误价）、`cost_usd`（`prompt_tokens` 视为 hit+miss 总量，hit 部分按 cache_read 折扣价、miss 按 input 价、cache_write 单列、completion 按 output 价；**未知模型返回 None 而非 0**，区分「免费」与「无价」）、`load_price_table`（合并 `MINICC_PRICING_JSON` 运行时覆盖，畸形条目静默忽略不抛）。接线：`benchmarks.py` 每行 result 落 `cost_usd`（report 的 `cost_per_success_usd`/`cost_available` 此前已消费该字段，现终于非空）；`task_manager.py` 两处 `snapshot()`（完整 + summary_only）落 `cost_usd`；`main.py` REPL 新增 `/cost`（跨轮累计 `tokens_used`，无价模型显式提示）；`web/src/panels/index.js::taskMetrics` 在 `cost_usd` 为数字时追加 `$` 段（已 `npm run build:web` 重新打包，`check:web` 通过）。`llm/fake.py` 三种响应补确定性 `usage`（prompt/completion 拆分），使成本链路无需真实模型即可观测。**附带修复**：`tests/test_task_durability.py::test_readonly_task_starts_without_copying_workspace_snapshot` 的 stub config 缺 `model` 字段，在前序会话给 `submit()` 加 `normalize_model_name` 后一直 400（与本任务无关的既有红），补 `model="test-model"` | `tests/test_pricing.py`（13 条）：固定 usage `cost_usd` 精确到 1e-6、未知模型 None、最长前缀、cache hit 折扣价、cache_write 单列、env 覆盖、畸形覆盖忽略、负计数钳零、fake provider + 显式单价跑 1 条任务后 `cost_per_success_usd` 非 None 且 >0、results.json 与 task snapshot 均不含 api_key；回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_task_durability`(9)、`test_task_worker`、`test_m4_evidence_chain`、`test_auto_resume`、`test_subagent_task`、`test_permission_modes`、`test_core`、`test_p0_p1_p2`、`test_http_surface`(56)；`reliability_probe` exit 0；fake provider 服务器下 `node tests/web_smoke.mjs` exit 0 |
| M4-T5 fixture 工作区 + edit fixture + hidden grader | ✅ | 新增 `benchmarks/tasks.v2.json`（24 条可写任务：write 12 / test-fix 6 / multi-file 6，file_contract 17 + command_contract 7，全部带 `fixture` 与正数 `max_minutes`）；新增 `minicc/bench_tasks.py`：`v2_tasks`/`validate_task`（必填键、id 唯一、fixture 路径逃逸拦截、grader 类型白名单、max_minutes>0）、`resolve_grader_dir`（显式参数 → `MINICC_EVAL_GRADER_DIR` → 仓库**外**同级 `.graders`，默认不落仓库内）、两类隐藏 grader 驱动脚本（`file_contract`：exists/contains/not_contains/equals/regex/json_equals；`command_contract`：`{python}` 占位符替换 + 期望退出码/stdout marker，并以 `PYTHONDONTWRITEBYTECODE=1` 跑命令避免 Windows 同 mtime 陈旧 .pyc 掩盖修复）、`grade_v2` 分发（签名对齐 `grade_behavior`）。`benchmarks.py`：`--suite v2`（加载即逐条 `validate_task`，失败 `parser.error`）、`--grader-dir`、`run_benchmark(grader_dir=...)`，grading 段按 grader 类型路由到 `grade_v2`；`build_report` 在无执行行时把 `grading_coverage` 回退为**定义级**覆盖率（声明 grader/verify_command 的任务占比）并新增 `gradable_task_count`，使 `--suite v2`（不带 `--run`）即可输出 coverage=1.0、分母≥24 而不烧模型。`tools/fs.py`：`.graders` 入 `SKIP_DIRS`（glob/grep/tree 递归不可见）+ `_reject_grader_dir` 在 read_file/write_file/edit_file/glob/grep/tree 直接命中 `.graders` 时抛 `ToolError`→`[TOOL_ERROR]`。**前提修正**：roadmap 列的 `benchmarks/fixture-workspaces/` 未单独建——v2 fixture 沿用既有 `prepare_fixture` 的内联 `fixture` 字典 + 独立 tempdir 机制（M4-T5「改什么」已确认隔离已存在），再建一份磁盘种子树只会与 tasks.v2.json 内容重复并引入漂移，故合成仓库以内联 fixture 表达 | `tests/test_bench_tasks.py`（12 条）：schema/id 唯一/≥24/类别下限、定义级 coverage=1.0 且分母≥24、fixture 逃逸/未知 grader/max_minutes≤0 均 `validate_task` 抛错、`resolve_grader_dir` 优先级且默认在仓库外、file_contract 种子态一过一败、json_equals+not_contains 判别、command_contract 修 bug 前后判别（独立工作区避 .pyc 竞态）、**fake provider 跑 2 条 file_contract 断言一过一败**、`read_file/grep/glob/tree` 打 `.graders` 全 `[TOOL_ERROR]`、递归 tree/glob/grep 不泄露 `.graders`/SECRET。`--suite v2`（无 --run）实测 `grading_coverage=1.0 gradable_task_count=24 pass_at_1=None`。**真实模型手动跑 2 条 edit fixture**（step-3.7-flash）：`v2-fix-add` completion.status=complete、含 `verification_required/observed/passed`+`completion_complete` 事件、4 次 write、command_contract grade passed=True；`v2-greeting-needs-fix` 触发上游 429（RPM 10）但已写入并 file_contract passed=True；两次运行后仓库 `git status --porcelain` 新增条目为 (none)，确认工作区外零写入。回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_pricing`(13)、`test_core`、`test_m4_evidence_chain`、`test_todo_tool`、`test_task_worker`、`test_web_security` |
| M4-T6 A/B 对比器与统计门槛 | ✅ | 新增 `minicc/bench_compare.py`：两份 `build_report` JSON（或裸 `results` 数组）逐任务对齐（共有 task_id 求交，独有任务进 `baseline_only_task_ids`/`variant_only_task_ids` 并出 note，绝不静默丢弃），输出 (1) pass@1 差值 + 每版 **Wilson 95% 得分区间**（小样本/极端比例仍落 [0,1]）+ 差值的 **Newcombe 混合得分区间**；(2) per-success cost 差值 + **配对 bootstrap 95% CI**（按 task_id 有放回重采样保配对，`random.Random(seed)` 确定性，默认 2000 次）；(3) latency P50/P95 差值（R-7 插值，与 `build_report._quantile` 同算法，本地实现避免与 `benchmarks` 循环导入）；(4) 按 category 分解的 pass@1 base/var/delta。`parse_gate` 解析 `metric>=|<=|>|<value`，仅认 `pass_at_1`/`cost_per_success_usd`/`latency_p95_ms`/`grading_coverage` 四类，对 **variant** 指标判定，指标为 None 时 **fail-closed**（视为违反，不可用 ≠ 达标）；任一违反 `main()` 返回 1 并打印 `[GATE FAILED]`。`--repeat N`：N<10 按路线图**不下 pass@k 结论**（仅出 note），N≥10 还需报告每任务携带 ≥N 次 `draws` 才用无偏估计 `1-C(n-c,k)/C(n,k)`（log 空间防溢出）计算，否则 note 说明无法计算。`--json-out`/`--junit-out`（每 gate 一 testcase，违反写 `<failure>`，XML 转义）。`render_delta_table` 输出人工可读 markdown delta 表。`benchmarks.py::main` 新增 `compare` 子命令派发（`raw[0]=="compare"` → 懒导入 `bench_compare.main(raw[1:])`，避免循环导入且不与报告解析器 flag 冲突），故 `python -m minicc.benchmarks compare --baseline a.json --variant b.json` 直接可用 | `tests/test_bench_compare.py`（22 条，先红后绿——首版 `_VAR_FLAGS` 误写 8/12 即被 `pass_at_1==0.75` 断言抓出）：Wilson 与独立闭式 `_ref_wilson` 逐项吻合到 1e-12、边界 0/0→None·0/5·5/5·越界抛错、Newcombe 与 `_ref_newcombe` 吻合、12 任务两版（6/12 vs 9/12）delta=0.25 且 CI 含真值、cost 差值精确 + bootstrap CI lo≤hi、P50/P95 差值与手算 `_ref_quantile` 吻合（variant 更快→负）、category 分解 delta 自洽、任务集不对齐出 note 且对齐数=11、无可评分行→delta=None（非 0）+note、repeat=3 不下 pass@k、repeat=10 无 draws 不下结论、带 draws 的 pass@k=1-11/66 与 1.0、`parse_gate` 各形态 + 未知指标/缺比较符/非数抛错、gate fail-closed、**`main()` gate 违反返回 1（pass_at_1>=0.9 对 0.75 必红）/ 满足返回 0**、写 json+junit、坏 gate/repeat<1 `SystemExit`、delta 表人工可读、junit 转义与失败计数、`benchmarks.main(["compare",...])` 派发。CLI 实跑：gate 满足 exit 0（delta 表含 pass@1 0.5→0.75、cost 0.02→0.0107、write 类 0.5→1.0）、gate `pass_at_1>=0.99` exit 1。回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_bench_tasks`(12)、`test_pricing`(13)、`test_core` |
| M4-T7 检索决策门（hit-rate 基线） | ✅ | 新增 `benchmarks/retrieval-hitrate.json`（`schema_version=retrieval-1`，20 条「已知答案定位」case：每条 = 开发者中英混合提问 + 应答的仓库相对文件 `targets`，全部经核实存在，覆盖 pricing/bench_compare/bench_tasks/retrieval/fs/registry/web/task_manager/mcp/config/fake/completion/verification_plan/tool_policy/loop/rpc/session/bash/editor/usage）；`benchmarks.py` 新增 `load_retrieval_cases`（校验对象/非空/id 唯一/非空 query/targets 为非空且不逃逸的相对路径列表/ks 为 ≥1 整数）、`evaluate_retrieval`（建一次 `LocalEvidenceIndex`，逐 case `search(query, limit=max(ks))`，`recall@k=|targets∩top-k|/|targets|` 按 case 求均值、MRR 取首命中排名倒数、附带 `hit@k` 与 per-case `first_relevant_rank`/`top`）、`retrieval_decision`（recall@5<0.6→建议评估本地 embedding 且须附 A/B；≥0.6→写下「不引入向量检索」并停止投入；None→无法判定保持现状）、`markdown_retrieval`、`_run_retrieval_suite`，`--suite` 扩为 `(legacy,behavior,v2,retrieval)`，retrieval 分支早返回（写 json+markdown、打印指标与结论、**返回 0 不门禁**）。**前提修正**：roadmap 说「用 12 条行为任务 + 30 条 fixture 的 trace 建基线」，但 trace 不含「问题→应命中文件」的标注真值，无法直接算 recall；改为人工标注 20 条定位真值（query→target file），在仓库自身上检索，这才是 hit-rate 的可证伪定义。书面结论落地 `docs/BENCHMARK_EVALUATION.md`「检索决策门（M4-T7）」节 | 实测 `--suite retrieval`：`recall@1=0.65 recall@5=0.90 MRR=0.75 cases=20` → 结论「不引入向量检索」（recall@5≥0.60）。`tests/test_retrieval_eval.py`（8 条）：真实数据集 schema/id 唯一/≥12/相对路径、6 类畸形数据集均 `ValueError`、合成工作区 recall@1==mrr==2/3 且故意 miss 的 case `first_relevant_rank is None`、多目标部分命中 recall≤0.5、决策三档阈值（==floor 通过/0.59 建议 embedding/None 无法判定）、**`test_real_dataset_clears_floor` 守护已提交结论**（recall@5 跌破门槛即红）、`main --suite retrieval` 写 json+md 含「结论」返回 0、坏数据集返回 2。回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_bench_tasks`(12)、`test_bench_compare`(22)、`test_core`、`test_pricing`(13) |
| M4-T8 CI 卫生 | ✅ | `pyproject.toml`：`httpx>=0.27.0` 进 **dev extra**（此前仅 `anthropic` extra 声明，CI 的 `pip install -e ".[dev]"` 靠 openai 传递依赖侥幸可用；`test_anthropic_provider`/`test_reasoning_effort` 与两个 provider 直接用 httpx），`addopts` 由 `-q` 改 **`-ra`**（输出通过计数 + skips/xfails/warnings/errors 短汇总，旧 `-q`+CI `-q`=-qq 把 warnings 汇总完全藏掉）。`.github/workflows/ci.yml`：(1) 触发器加 `schedule`（cron `17 18 * * *`，避开整点调度高峰）+ `workflow_dispatch`；(2) `pytest` job 安装后加 **`pip check`**、跑 `--junitxml=junit-${os}.xml` 并 `if: always()` 上传 artifact（去掉与 addopts 叠加成 `-qq` 的 `-q`）；(3) `js-check` 补 `node --check tests/codex_smoke.mjs`；(4) `web-smoke` job 在 `test:web` 后新增 **`npm run test:arcade`** 步骤，复用已起的 fake-provider 服务器跑 game/codex/zombie 三套此前**只签入不执行**的 Playwright 套件；(5) 新增 **`eval-pr`** job（`if: != schedule`，`timeout-minutes: 15`，fake provider 跑 `--suite behavior --run`，断言 `execution_completion_rate==1.0 且 grading_coverage==1.0` 的**流程门**——fake 不解题故 pass_at_1 恒 0，不卡准确率，上传报告 artifact）；(6) 新增 **`eval-nightly`** job（`if: schedule||workflow_dispatch`，真实 `secrets.MINICC_API_KEY` 跑 `--suite v2 --run`，再用 `benchmarks compare` **自比**（baseline==variant）施加绝对门槛 `pass_at_1>=0.3`/`grading_coverage>=0.9`/`latency_p95_ms<=600000` 并出 JUnit，`if: always()` 上传 v2+compare+junit artifact；初值保守待真实准确率画像后逐步上调）。`package.json`：补 `test:codex`/`test:zombie` runner + `test:arcade`（串三套游戏套件），`test:all` 改为 `test:web && test:arcade`。**前提修正**：roadmap 称 `codex_smoke.mjs`「无 runner 且引用不存在的 `zombie_spawn_smoke.mjs`，完全孤立」应删除——经核实 `zombie_spawn_smoke.mjs` **存在**、`codex_smoke.mjs` 全文**不引用**它，且 codex_smoke 是 101 行真实可用的 Playwright 套件（本地对 fake-provider 服务器实跑：game/codex/zombie 三套全 passed）。删除会损失真实覆盖，与本任务「5 个套件全进 CI」意图相反，故改为**补 runner 并接入 CI**而非删除 | 本地实测：`pip check`→`No broken requirements found`；`pytest tests/ --collect-only`→**605 tests collected**（dev extra 装齐后可全收集）；`-ra` 实跑显示 `22 passed`；fake-provider 服务器（:8791）下 `npm run test:game/test:codex/test:zombie` 三套**全 exit 0**（19 plants+19 zombies / 18 wave types 校验通过）；`--suite behavior --run`（fake，全 12 条）`execution_completion_rate=1.0 grading_coverage=1.0 pass_at_1=0.0`，PR 流程门阈值确定。`ci.yml` 经 `yaml.safe_load` 校验合法，jobs=`{pytest,reliability-probe,js-check,web-smoke,web-smoke-mutation,eval-pr,eval-nightly}`、triggers 含 schedule/workflow_dispatch。新增 `tests/test_ci_hygiene.py`（7 条，tomllib+json+ci.yml 文本断言）：httpx 在 dev extra、addopts 含 `-ra` 且非 `-q`、CI 有 `pip check`+`--junitxml`+artifact、eval-pr/eval-nightly 双 job 与各自门、每个 Playwright 套件有 runner 且 `test:arcade` 进 CI、codex_smoke 未被删 |
| M4-T9 清理与文档可信度 | ✅ | **死包与产物**：仓库根的 shell 重定向垃圾 `=0.5`/`=0.99`（早前 `--gate pass_at_1>=0.5` 未加引号产生）删除；`scripts/build-web.mjs` 改为打包后按 `asset-manifest.json` 反推 `referenced` 集合、`readdirSync(web/assets)` 取磁盘集合，`stale=磁盘-referenced` 在构建模式 `rmSync` 逐个清除（打印 `pruned N stale asset bundle(s)`）、在 `--check` 模式打印错误并置 `process.exitCode=1`（`npm run check:web` 从此把陈旧 bundle 视为失败）。一次 `npm run build:web` 剪除 **24 个**死 bundle，`web/assets/` 收敛为恰好 3 个被 manifest 引用的文件（app/game js + styles css）。**`web/app.min.js` 退役**：删 build-web.mjs 里 `if (name==="app.js" && !check) writeFileSync(...app.min.js...)` 生成行、删磁盘文件、删 `.gitignore` 的 `web/app.min.js` 条目（`static_assets.py` 只服务 manifest 引用的资源，该 min 包早已无人引用）。**版本单一来源**：`pyproject.toml` 去掉静态 `version="0.1.0"`、改 `dynamic=["version"]` + `[tool.setuptools.dynamic] version={attr="minicc.__version__"}`；`main.py` `from . import __version__` 且 `--version` 用 `f"minicc {__version__}"`；`mcp.py` 两处 clientInfo 由硬编码 `"0.2.0"` 改 `{"name":"minicc","version":__version__}`（消除 mcp 声明版本与包版本漂移）。**文档同步**：`README.md` 示例 allowlist 的死脚本 `npm run typecheck`→`npm run test:optimization`；`docs/BENCHMARK_EVALUATION.md` 陈旧「2026-09-18 本轮结果：23 项通过（9.78 秒）」按当前命令实跑改为逐字 `27 passed in 9.48s`（2026-09-21 复现） | 新增 `tests/test_cleanup_version.py`（7 条）：pyproject `dynamic` 含 version、`minicc.__version__==importlib.metadata.version("minicc")==mcp.__version__`（且 mcp.py 源码含 `"version": __version__` 且无 `"version": "0.` 硬编码）、子进程 `python -m minicc.main --version` 输出 `minicc 0.1.0`、`web/app.min.js` 不存在且 build-web.mjs 不含 `app.min.js`、`web/assets/` 磁盘集合==manifest 引用集合且 len==3、仓库根无 `=0.5`/`=0.99`/`pytest_full.*` 等复现产物、README 无死 npm 脚本。实测：`minicc.__version__==importlib.metadata.version("minicc")==mcp.__version__==0.1.0`、`python -m minicc.main --version`→`minicc 0.1.0`、`npm run check:web`→`web/assets is clean (3 referenced bundle(s))`（植入假死包后正确转红）、`pip install -e .` 后重装校验通过。回归全绿：`test_cleanup_version`(7)、`test_ci_hygiene`(7)、`test_optimization_core`（合计 22 passed in 6.25s） |

### 已完成（M5 MCP 桥加固与 CLI 接线，全部）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M5-T1 render() 输出截断（HIGH） | ✅ | `mcp.py` 新增模块级 `_content_to_tool_result(server, tool, result)`：把 MCP `content` 拼成文本后走 `tools.registry.split_output`，落 `head/tail/truncated`（与 fs/bash/git 等内置工具同一 6000 字符预算 HEAD=2000+TAIL=4000），`output` 不再直灌全文；stdio 与 http 两个 `call_tool` 统一改用该 helper（消除两处重复的 content 扁平化）。顺手删除文件顶部**重复定义**的第二个 `class McpError` | `tests/test_mcp_stdio.py::test_half_million_char_output_is_truncated`：假服务器 `tools/call` 返回 50 万字符，断言 `truncated is True`、`len(output)<=6000`、`len(head)<=2000`、`len(tail)<=4000`、`render()` 含「输出已截断」且 <7000；`test_small_output_not_truncated` 短输出 `truncated is False`。**既有 `test_mcp_http.py::test_http_client_handshake_tools_and_call` 按 A.3-2 改写**：原断言 `"echo: 你好" in result.output` 正是本任务要消灭的「output 直灌全文」缺陷语义，改为断言 `result.render()`（模型实际可见面）并加注释说明 |
| M5-T2 id 类型容错与解析失败全包 McpError（HIGH） | ✅ | `mcp.py`：stdio `_request` 与 http `_parse_body` 的 id 匹配由 `response.get("id")==request_id` / `int(event.get("id") or -1)==expect_id`（对合法 JSON-RPC **string id** 抛裸 `ValueError`）改为两侧 `str(...)==str(...)` 规范比较；http `_parse_body`/`_request` 的 result 非 dict 时返回 `{}` 而非 `None or {}` 的隐式塌缩。stdio `_read_loop` 区分**服务器主动请求**（含 `method`）与响应（含 `id` 无 `method`）：新增 `_handle_server_message` 对 `ping`→`{}`、`roots/list`→`{"roots":[]}` 应答、其余回 JSON-RPC `-32601`，不再静默丢弃。`webserver.py`：`import McpError` 并把它加入 `do_POST` 的 **400 结构化错误** except 元组（此前 `McpError` 是 `RuntimeError` 子类，会落到兜底 `except Exception`→**500「agent failed」**） | `tests/test_mcp_stdio.py::test_string_id_response_is_matched`（假服务器 `string_id=True` 回显字符串 id，`call_tool` 仍 `status=="ok"` 且取回文本）、`test_server_initiated_ping_is_answered`（假服务器在 `tools/call` 时反向发 `ping`，只有客户端应答了才回 `pong`，断言 render 含 `pong` 且不含 `no-response`）。回归 `test_mcp_http`(全绿)、`test_http_surface`(56)、`test_web_security` |
| M5-T3 stdio reader 监督与负缓存（MEDIUM） | ✅ | `mcp.py`：`Popen` 的 stdout 加 `errors="replace"`（不可解码字节不再杀死 reader 线程）；`_read_loop` 全包 `try/except (OSError,ValueError)/finally`，**任何退出路径都 `_mark_dead`**；新增 `dead` property（`_dead or process.poll() is not None`）、`_ensure_alive()`（dead/退出即抛 `McpError`）。`_request` 改为 `deadline=time.monotonic()+timeout` + `self._responses.get(timeout=min(remaining,0.25))` 短切片轮询，每次 `queue.Empty` 复查 `_ensure_alive`——中毒后**首次调用即快速失败**而非恒等满 30s；id 采番移入 `_write_lock`（`_write_locked`）避免并发竞态，写锁只在「采番+帧写」期间持有、等待响应前释放（reader 才能应答服务器主动请求）。`McpManager` 新增 `_client_lock` + **负缓存哨兵 `_DEAD_CLIENT`**：client 构建抛 `McpError` 即缓存哨兵，后续 `_client` 直接抛错**不再重复 spawn** | `tests/test_mcp_stdio.py::test_undecodable_stdout_fails_fast_not_30s`（假服务器 `tools/list` 时写 `b"\xff\xfe\x00bad\n"` 后退出：首调 <5s 抛 `McpError` 且 `client.dead is True`，二调 <1s 抛错）、`test_manager_negative_cache_does_not_respawn`（`python -c "raise SystemExit(3)"` 的 ghost server，两次 `tool_specs()` 均抛 `McpError`，断言 `.minicc/mcp_audit.jsonl` **只有 1 行**=只 spawn 过一次） |
| M5-T4 工具名 128 字符截断与冲突（MEDIUM） | ✅ | `mcp.py`：`tool_specs` 内 `safe_name=f"mcp__{name}__{tool}"[:128]`（两个仅在第 128 字符后不同的长名会截断成同名，令 `ToolRegistry.register` 抛**未捕获 `ValueError`** 绕过 web 的 `except McpError`）改为新增 `_unique_tool_name(server, tool, taken)`：短名原样返回；超长/冲突名用 `sha256(full_name)[:8]` 短哈希后缀（`base[:119]~xxxxxxxx`，恒 ≤128）确定性地消歧，`taken` 集合兜底再哈希。两个工具都保持可调用而非毒化整个 workspace | `tests/test_mcp_stdio.py::test_long_tool_name_collision_is_disambiguated`：假服务器列两个 `"x"*128+"_alpha"/"_beta"` 工具，断言 `tool_specs()` 返回 2 个**互异**且 ≤128 的名字，且把两个 spec 依次 `registry.register` **不抛 ValueError**（旧截断实现下必红） |
| M5-T5 close() reap 子进程与部分启动失败（LOW） | ✅ | `mcp.py`：`McpStdioClient.close()` 由「只 `terminate()` 不 wait/kill/关管道」（POSIX 成僵尸、SIGTERM-ignoring server 继续跑）改为 `terminate→wait(3)→kill→wait(3)` + `finally` 关 stdin/stdout + `_mark_dead("closed")`；`_start` 的 `initialize`/`notifications/initialized` 包 `try/except McpError: close(); raise`（半启动 child 不残留）。`McpManager.tool_specs` 包 `try/except McpError`：发现某 server dead 或 `list_tools` 抛错即 `_mark_dead(reap=本次新 spawn)`，并在外层把**本次调用新 spawn 的其余 child 一并 reap**——第二个 server 失败不再让第一个 child 无主 | `tests/test_mcp_stdio.py::test_close_reaps_child_process`（构造后 `process.poll() is None`，`close()` 后 `poll() is not None`=已收割无僵尸）；负缓存/reap 路径由 `test_manager_negative_cache_does_not_respawn`、`test_dead_server_marked_in_health` 覆盖 |
| M5-T6 CLI 接入 MCP | ✅ | `main.py`：`from .mcp import McpError, McpManager`；`run()` 前当 `workspace/.minicc/mcp.json` 存在时构建 `McpManager`（构建抛 `McpError` 则打印 `[mcp] 配置不可用，已忽略` 并退回 `None`），`build_registry(editor, yolo=..., mcp_manager=mcp_manager)` 接线，`/tools` 即列出 `mcp__` 工具；`run()` 的 `finally` 在 `provider.close()` 后 `mcp_manager.close()` 收割子进程。**无 mcp.json 时 manager 为 None，registry 行为与改前完全一致**（不 spawn、不加工具）。README:24「可选 MCP stdio 工具桥：读取工作区 .minicc/mcp.json」自此对 CLI 与 web 同时成立，无需删表述 | `tests/test_mcp_stdio.py::test_build_registry_lists_mcp_tools`（有 mcp.json 的 workspace 经 `build_registry(..., mcp_manager=manager)` 后 `registry.names()` 含 `mcp__srv__` 前缀工具）；`python -m minicc.main --version`→`minicc 0.1.0`（CLI 导入链未破坏）；回归 `test_core`、`test_cleanup_version`(含 CLI 子进程断言) 全绿 |
| M5-T7 MCP resources/prompts 与工具健康检查 | ✅ | `mcp.py`：stdio+http 客户端各补 `list_resources()`/`list_prompts()`（请求失败吞成 `[]`，不毒化发现流程）；`McpManager.resources_context(max_chars=6000, max_items=20)` 把 `resources/list`+`prompts/list` 拼成**逐行 ≤6000 字符**的只读上下文（dead/不可达 server 跳过并 `_mark_dead`）；`McpManager.health()` 不 spawn 地回报每个 server `ok/dead/unspawned`；`tool_specs`/`_client` 对 dead client 立即抛结构化 `McpError`（「不可用（已标记 dead）」/负缓存）。`web.py::_chat_locked` 在本地检索索引注入之后追加「[MCP 只读上下文]」system 消息（manager 为 None 或 `resources_context` 抛 `McpError`/空白则跳过），并复用同一 `mcp_manager` 局部变量给 `build_registry`（不再二次 `_mcp_for_workspace`）。**`sampling` 按第四节显式延后**（让远端 server 反向驱动本地 agent，安全模型未设计前不做） | `tests/test_mcp_stdio.py::test_resources_context_is_bounded_and_injected`（假服务器 `resources/list` 带 7000 字符 description + `prompts/list`，断言 context 含 `file:///big`/`summarize` 且每行 ≤6000）、`test_dead_server_marked_in_health`（`garbage_on_list` server 令 `tool_specs` 抛 `McpError` 后 `health()` 报 `srv=="dead"`，且再次 `tool_specs` <1s 抛错=负缓存）。**新增 `tests/test_mcp_stdio.py` 共 11 条表驱动单测**（≥8 退出标准达成），全部起真实子进程跑内联 JSON-RPC 假服务器（不 mock subprocess），覆盖 T1–T7。回归：`test_mcp_stdio`(11)+`test_mcp_http`(8)+`test_security_perimeter`+`test_m1_integrity`+`test_core` 合计 164 passed；`test_http_surface`(56)+`test_p0_p1_p2`+`test_git_workflow`+`test_subagent_task`+`test_todo_tool` 合计 91 passed；`test_web_security`+`test_cleanup_version` 24 passed |

### 已完成（M6 能力扩展 I）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M6-T1 subagent 可写档有界深度与预算 | ✅ | `minicc/agent/subagent.py`：新增三层工具集常量 `WRITE_TOOLS`/`EXEC_TOOLS`/`SUBAGENT_TOOL_TIERS`（readonly=原 `SUBAGENT_TOOLS` ⊂ write=+`write_file`,`edit_file` ⊂ exec=+`bash`；**三层均不含网络工具、不含 `task`**）与授权门 `WRITABLE_PERMISSION_MODES={acceptEdits,yolo,bypassPermissions}`、`EXEC_PERMISSION_MODES={yolo,bypassPermissions}`（子代理无法弹审批框，故写能力只能继承父会话已授予的模式）。`resolve_subagent_tier(*, writable, permission_mode)` 决定档位：未开 `writable` 或模式不在可写集合 → 一律 `readonly`（**默认零回归**）。`build_task_tool_spec` 新增 `depth/max_depth/writable/permission_mode/allow_network/max_tokens/soft_max_tokens/soft_max_duration_seconds` 形参，`spec.risk` 由 `readonly`/`write` 区分，description 按档位说明能力边界。`_SubagentRunner._child_registry()` 用 `base_registry.restrict(SUBAGENT_TOOL_TIERS[tier])`，深度门 `can_delegate = tier != "readonly" and depth + 2 <= max_depth`（`DEFAULT_MAX_DEPTH=2`）——到达最大深度时 `task` 工具**结构上不存在**，第 3 层递归不可能。`_child_budget()` 构造 `Budget(max_turns/max_tokens/soft_max_tokens/soft_max_duration_seconds)` 传入 `run_agent`；新增 `except BudgetExceeded` 分支：置 `child_cancel`、`join(15s)`，返回结构化 `[BUDGET] 子代理预算耗尽` 的 error `ToolResult`（`data.budget_exceeded=True`、`security_tags=["untrusted","subagent"]`），**不拖垮父会话**。write/exec 档在 prompt 里加模式注记，明示「子代理输出对父级不可信、必须引用证据」。并发上限 3（`_SUBAGENT_SLOTS`）不变。`config.py`：`subagent_writable`（`MINICC_SUBAGENT_WRITABLE`）、`subagent_max_tokens`、`subagent_max_depth`（`max(1,min(2,int))` 钳制、非整数抛 `ConfigError`），`describe()` 输出 `subagent=delegated(depth<=N)` / `subagent=readonly`。`main.py` 新增 `--subagent-writable` 并向下传递 `permission_mode`/`allow_network`；`web.py` 从 config 读取档位参数接线 | 新增 `tests/test_subagent_delegation.py`（16 条，先红后绿）：`resolve_subagent_tier` 7 组参数化、exec 档需显式授权且三层均无网络工具、readonly 子注册表**不含 `task`**（结构断言）+ `spec.risk=="readonly"`、writable 档 `risk=="write"`、深度门（depth0 可写 → 子名字含 `task`；depth1 → 不含 ⇒ 第 3 层不可能）、`max_depth=1` 无嵌套、`_child_budget` 字段映射、`monkeypatch` 令 `run_agent` 抛 `BudgetExceeded` 断言 `[BUDGET]`+`data.budget_exceeded`+untrusted 标签、正常路径回传 untrusted、并发第 4 个被拒。回归 `test_core`+`test_http_surface`+`test_p0_p1_p2`+`test_subagent_task`+`test_subagent_delegation`+`test_model_fallback` 合计 **214 passed**；环境变量实测 `MINICC_SUBAGENT_WRITABLE=1 MINICC_SUBAGENT_MAX_DEPTH=5` → `writable=True depth=2`、`describe()` 含 `subagent=delegated(depth<=2)` |

| M6-T2 子代理进度可见、可取消、计入父预算 | ✅ | `minicc/agent/subagent.py`：`build_task_tool_spec`/`_SubagentRunner` 新增 `on_trace` 父级事件汇与 `parent_trace_id`；`_run_bounded` 为每次运行生成 `run_id`，用 `lifecycle()` 发 `subagent_started/progress/cancelled/budget_exceeded/timed_out/finished` 结构化事件、用 `bubble()` 把子 `run_agent` 自身 trace 打上 `parent_id`/`subagent`/`depth` 冒泡到父汇（`_emit` 吞异常，遥测不拖垮执行）。**把 `future.result(timeout=600)` 整段阻塞改为有界轮询**（`WAIT_POLL_SECONDS=0.25` 切片 + `PROGRESS_EMIT_SECONDS=5.0` 心跳），每片检查父 `cancel_event` 即早退，超时/取消/`AgentCancelled`/`BudgetExceeded` 各自收敛并发对应 lifecycle。`_child_registry` 把 `on_trace`/`parent_trace_id` 透传给嵌套 `task`（孙代事件仍冒泡到同一父汇）。`minicc/agent/graph.py`：新增纯函数 `node_budget_from(parent)`（节点继承会话 `soft_max_tokens`/`soft_max_duration_seconds`，并把 soft token 上限当作节点硬 `max_tokens`，越限即 `BudgetExceeded`→`budget_exceeded` 而不再无界跑）与 `aggregate_dag_tokens(outputs)`。`minicc/web.py`：`run_node` 的**全 None Budget 换成 `node_budget_from(runtime_state.budget)`**，节点输出加 `budget_exceeded`；`execute_dag` 后用 `aggregate_dag_tokens` 求和并 `runtime_state.budget.record_usage` **回填父预算**（超限发 `planner` `budget_exceeded` trace 而非静默）；`build_task_tool_spec` 注册处接 `on_trace=on_subagent_trace` 令子代理进度进入实时 SSE。`minicc/main.py`：CLI 注册处接 `_cli_subagent_trace`（终端只打印 `subagent_*` lifecycle，不刷屏子内部轮次） | 新增 `tests/test_subagent_streaming.py`（5 条）：真实子代理线程 + `ScriptedProvider` 收集 `on_trace`，断言 ≥3 条 `subagent` 事件、全部共享单一 `parent_id`、`depth==1`、含 `subagent_started`/`subagent_finished`（`detail.tokens_used==45`）；`EndlessSlowProvider` + 0.5s 后置 `cancel_event` 断言 `status=="cancelled"` 且墙钟 <5s（非等 30s）；`node_budget_from` 把 soft=1000 变硬 `max_tokens`、越限 `pytest.raises(BudgetExceeded)`；`aggregate_dag_tokens` 求和 350 并回填 `Budget.tokens==350`。回归 `test_core`+`test_p0_p1_p2`+`test_http_surface`+`test_optimization_core`+`test_task_worker`+`test_web_security` 合计 **218 passed**；`test_subagent_streaming`+`test_subagent_task`+`test_subagent_delegation` 27 passed；`python -m minicc.main --version`→`minicc 0.1.0` |

| M6-T3 写/exec 工具并行执行 | ✅ | `minicc/agent/loop.py`：一轮工具调用里，此前只有只读调用 fan-out（`asyncio.to_thread`），`write_file`/`edit_file`/`bash` 全部在 `for index` 循环里**串行阻塞**执行，多文件改造的 latency 全耗在等 IO。改为**写阶段**：新增模块级 `_parallel_write_key(tool, arguments)`（仅 `PARALLEL_SAFE_WRITE_TOOLS={write_file,edit_file}` 且有非空 `path` 时返回 `write:<path>` 作序列化键，键只看 path 让同一文件的 write 与 edit 也互斥）与 `_run_write_phase(...)`/`_execute_and_store(...)`。循环内把非只读调用按是否可并行分流进 `pending_writes`（带 key）与 `serial_writes`（bash/todo_write/worktree_*/MCP 等）；`result.cancelled` 后、只读 fan-out **之前** `await _run_write_phase`：按 path key 分组，每组内按 index 顺序串行、不同组 `asyncio.gather(return_exceptions=True)` 并发，其余非只读工具作为**单个确定性串行组**。这样既让不同文件的写并发，又保住「写先于读」偏序（写阶段整体早于只读 gather）与「同文件写有序」（第二个 edit 看到第一个结果）。`_execute_and_store` 用 try/except 兜底，保证每个 index 一定拿到结果 → 一个写失败不丢其余结果、也不破坏 tool-call/结果对齐 | 新增 `tests/test_parallel_writes.py`（5 条）：假 `write_file`/`edit_file` 各 `sleep`，4 个不同 path 的写断言墙钟 **<0.6s**（串行基线约 1.2s）且 4 个结果全 ok；同 path 两个 `edit_file` 断言事件序列 `start,end,start,end`（无重叠=串行）且都拿到结果；一个 path 故意失败断言 3 个结果齐全、失败项 error、其余 ok；`_parallel_write_key` 对 bash/空 path/非 dict 返回 None；并发计数器断言 3 个不同 path 写的活跃窗口重叠（`peak>=2`，防退化回串行）。回归 `test_core`+`test_p0_p1_p2`+`test_optimization_core`+`test_http_surface` 合计 **196 passed** |

### 已完成（M7 生态与配置，全部）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M7-T1 Hooks（PreToolUse / PostToolUse / UserPromptSubmit / Stop） | ✅ | 新增 `minicc/hooks.py`：四事件契约（PreToolUse 只能**拒绝**、不能放行 `authorize_tool` 已拒的调用；Post/Stop 只审计；UserPromptSubmit 可阻断），配置在 `<workspace>/.minicc/hooks.json`（默认关闭、属 M2-T2 敏感文件 ⇒ agent 装不了 hook），子进程 cwd 钉在工作区且环境被清洗（`MINICC_API_KEY`/web token 不外泄），stdout/stderr 先脱敏截断再入 trace，超时 tree-kill、失败默认只记审计不阻断主流程 | `tests/test_hooks.py`；提交 `d88ad63` |
| M7-T2 自定义 slash 命令 + Skills 发现 | ✅ | `<workspace>/.minicc/commands/<name>.md`（project 优先）与 `~/.minicc/commands/`（user），支持 front matter 与 `$ARGUMENTS`/`$1..$9`，CLI 与 Web 输入均由服务端展开为普通 user 内容（同 AGENTS.md：不能改写系统指令与权限边界）；Skills 从 `.minicc/skills/<name>/SKILL.md` 发现，系统提示只注入 name + description，正文按需由 agent 读取 | `tests/test_slash_commands.py`；提交 `d7b0516` |
| M7-T3 Web 交互式权限审批 + 声明式 allow/deny | ✅ | Web 端把 `missing_task_write` / `missing_task_exec` 变成前端审批弹窗（允许后继续、拒绝落 `tool_denied_by_policy` 审计）；新增 `minicc/permissions.json` 规则层：`deny` 绝对且在询问前短路、任务开关与 allow 都越不过，`allow` 只跳过交互提示、绝不升级（plan 仍只读、联网仍需任务级授权），文件损坏时忽略规则并把解析错误进审计 | `tests/test_permissions_approval.py`；提交 `1da701a` |
| M7-T4 项目级配置层 + config.py 剩余缺陷 | ✅ | `.minicc/config.json` 逐键覆盖 user 级 `~/.minicc/config.json`，`config.load_config()` 的解析顺序为 args > 环境变量 > `.env` > project > user > defaults；新增 10 个 CLI 开关，修 `config.py` 六处解析/钳制缺陷 | `tests/test_project_config.py`；提交 `2b9f7fd` |
| M7-T5 前端数据丢失修复 + @-提及内容注入 | ✅ | `web/src/chat/stream.js` 失败恢复（提交失败不清空已输入内容），`minicc/mentions.py` 把 `@relative/path` 变成有界内容块附加到 user 消息：只读工作区相对路径（绝对/`~`/盘符拒绝，`resolve()+is_relative_to()` 拦 junction 越界），逐文件与整条消息双上限、截断处标 `[truncated]`，敏感与二进制引用只标注不读取，正文过 `redact_text` | `tests/test_mentions.py`；提交 `8ec2de0` |

### 已完成（M8 可分发与长期演进，M8-T1..T13）

| 任务 | 状态 | 落地位置 | 验证 |
| --- | --- | --- | --- |
| M8-T1 长期记忆 MEMORY.md + 自动召回 | ✅ | `memory_write/memory_read/memory_list` 写 `~/.minicc/MEMORY.md` 与 `<workspace>/.minicc/MEMORY.md`，落盘前 `redact_text`，系统提示只注入条目索引（≥200 条时最近 50 条） | `tests/test_memory.py`（17 条）+ 真实 API E2E（任务 A 写入的记忆出现在任务 B 的系统提示里）；提交 `45581fb` |
| M8-T2 会话 fork / 分支 | ✅ | `session.py` message 级事件树 + 稳定 `m-*` id + `fork(from_message_id)` 独立分支文件；CLI `--fork-from/--new-session-id/--list-sessions` 与 `/api/sessions/fork` 共用同一条 lineage；保存改为跨进程锁下重试 `os.replace`（Windows 上无锁读句柄会让替换失败并丢文件） | `tests/test_session_fork.py` + 真实 API E2E（第 2 轮答复处 fork，分支继承基准编号且不动源会话）；提交 `6b220cc` |
| （附带）完成评估不收敛与内部 id 泄漏 | ✅ | `agent/completion.py`：证据包补对话记录（`message-N`），`next_action: null` 视为「无事可做」而非协议错误，评估器自身故障走有界重试后归为 `unknown`；不再要求模型引用它看不到的 `event-N` 词汇 | `tests/test_completion_liveness.py`（含 8 条 null/类型回归）+ 真实 API 诊断日志定位；提交 `a0b17e3` |
| M8-T3 插件 API 稳定化 | ✅ | `tools/registry.py`：`TOOL_API_VERSION` + `ToolSpec.api_version/capabilities`、注册期 `validate_tool_spec`（名字/risk/params/input_schema/能力与风险自相矛盾全部拒绝并报出工具与字段）、同名冲突必须显式 `override=True` 且留 `overrides()` 痕迹；`capabilities` 里 `network` 让第三方只读工具走与内置 `web_search/webfetch` 同一道 `allow_network` 门（`audit.tool_requires_authorization/authorize_tool` + loop/main/web 三处接线）。`docs/PLUGIN_API.md` 为契约文档，示例代码块由测试原样执行 | `tests/test_plugin_api.py`（44 条，含 18 条非法 spec 与文档执行）+ 真实 API E2E（模型自行发现并调用 `line_count` 插件、内置 `read_file` 未被遮蔽、`url_head` 无授权时 `missing_task_network` 拒绝、授权后返回真实 HTTP 200）；提交 `40b9771` |
| M8-T4 可安装产物 | ✅ | `setup.py` 的 `build_py` 钩子在构建期把仓库根的 `web/`、`ide/` 复制进包内 `minicc/web_static`、`minicc/ide_static`（`MANIFEST.in` 同步进 sdist，保证从 sdist 再构建的 wheel 一致）；`static_assets.web_root()/ide_root()` 先查安装目录再退回 checkout，`webserver.STATIC_ROOT` 改用它；新增 `scripts/build-dist.ps1`（可选 `npm run build:web` → wheel+sdist → 校验 manifest 引用的 bundle 真的在包里）；`build-system` 提到 `setuptools>=70.1`（自带 bdist_wheel）；README 增加安装到别的机器的完整命令，并声明版本单一来源 | `tests/test_packaging.py`（11 条：包载荷、无 node_modules/`.env`/`__pycache__` 垃圾、console scripts 可解析、版本四处一致、README 引用的 npm 脚本全部存在、sdist round-trip 载荷集合相同、安装后从 site-packages 真的返回 index.html 与 bundle）+ 真实安装 E2E（`pip wheel . -w dist` → 干净 venv 安装 → `minicc --version`=`minicc 0.1.0` → `minicc-web --port 8791` 返回 `/` 200 与 3 个 hash bundle 200 → `/api/health` 200） |
| M8-T5 logging 取代 print + `/api/metrics` + 日志脱敏 | ✅ | 新增 `minicc/cli_io.py`（包内**唯一** `print()`，stdout 只承载 CLI/REPL 协议正文）与 `minicc/logging_setup.py`（默认 `WARNING`→**stderr**，`MINICC_LOG_LEVEL`/`MINICC_LOG_FILE`，每 handler 挂 `SecretRedactionFilter`，启动时 `register_secret()` 注册已解析 api key 与 web token 做精确子串掩码，脱敏幂等：`[REDACTED:…]` 标记内不再二次掩码）。审计事件、provider 重试、预算/事件树、任务生命周期、hook 执行、MCP spawn 统一走结构化日志，且每条都来自生产路径的单点插桩：`task_manager._run.on_event` 与 `task_worker._run_owned_worker.on_event`（thread/process 两个执行器同一词表）、`openai_provider` 的 `_status_logging_callback`（无回调也记，CLI 同样可观测）、`hooks.run()`、`mcp` spawn 审计写入处、`tools/editor._audit()`（`info/notice/warning` → `DEBUG/INFO/WARNING`）。`/api/audit` 增加 `level`/`min_level` 过滤（未知级别 400 并列出可选值，旧记录按 action 回填级别），新增 `/api/metrics`（`minicc.metrics.v1`：逐任务快照累加 `tokens_used`/`cost_usd`，未计价模型单独计 `unpriced_tasks`，不混作 0 成本）；`webserver._fail()` + `ERROR_CODES` 让失败响应带稳定 `code`（`forbidden`/`task_not_found`/`unauthorized`/`invalid_request`/`internal_error`），不再只有一句话的裸 500。`minicc.config.example` 与 README 补日志章节 | `tests/test_logging.py`（22 条）：fake provider 任务在 `MINICC_LOG_LEVEL=DEBUG`+`LOG_FILE` 下 grep 断言含 `provider_retry`/`tool_round_finished`/`run_finished`、不含 api_key 与 web token（两个常量刻意不匹配任何密钥形态，缺席只能由注册式掩码解释）、级别/文件/stdout 纯净、脱敏幂等与 8 种密钥形态、`/api/metrics` 与单任务快照逐项对账、审计级别过滤、错误码映射。print 口径见下方注记。真实 API E2E：CLI 与 `minicc-web` 各跑一次真实任务，日志 299 行（97 DEBUG / 201 INFO / 1 ERROR）中 key 与 token 均无命中，`/api/metrics` 的 token/成本与任务快照精确相等，未计价模型走 `unpriced_tasks` |
| M8-T6 `tests/test_core.py` 按 domain 拆分 | ✅ | 2964 行 / 109 个测试的单文件巨块拆成 `test_core_{agent,tools,task,llm,session}.py` 五个领域文件，另有 4 条跨域测试留在 `tests/test_core.py`（原因见下方注记）。测试本体逐字搬迁、断言零修改；每个文件只保留自己用到的 import（AST 名称 + monkeypatch 字符串路径双判据），六个文件均无未使用导入 | `pytest --collect-only -q` 拆分前后同为 **853 tests collected**；全量 `pytest -q` 三次实测：拆分前 230.06s，拆分后 222.08s 与 234.50s，均值 228.3s——差异在单机 ±3% 抖动内，**未观察到系统性上升**（本机非 CI 环境，墙钟本身不是稳定量）；六个文件单跑 116 passed；AST 逐函数比对确认 109 个测试各出现一次且与 `HEAD` 逐字相同；CI 的 `pytest tests/` 不点名本文件，workflow 无需改 |
| M8-T7 评审器故障分类：确定性拒绝不再重跑 agent | ✅ | 源自 M8-T5 真实运行遗留观察（详见下方注记）。`llm/openai_provider.py` 新增 `classify_provider_failure(exc) -> bool \| None`：`True`=传输/配额类可重试，`False`=提供方按策略拒绝（内容拦截、凭据错误、参数不支持），`None`=异常根本不经过这条 HTTP 栈（Anthropic 路径抛自己的 `RuntimeError`、或调用方构造证据包时就出错）——**不给结论**，调用方保持原保守行为。`agent/completion.py` 的 `CompletionDecision` 新增三态字段 `review_transient`（刻意不进 `to_dict()`：它是给调用方的控制流，不是用户可见数据），兜底 `except Exception` 用**异常对象**判定而非字符串。`web.py` 在 `review_transient is False` 时发 `completion_judge_rejected` 结构化 trace 并以「完成评估请求被模型端拒绝：…」结束任务、直接 `break`，不再走 `completion_judge_retry` 那条「重跑整轮 agent 再问一次」的路；`True`/`None` 保留原有的一次有界自检。错误文案刻意以「完成评估」开头，使 `judge_unavailable → ignore_result_error` 的既有判定继续成立 | `tests/test_completion_liveness.py` 22 → 31 条：异常家族判定表（400/401 → `False`，`APIConnectionError` → `True`，`RuntimeError("Anthropic HTTP 451…")` 与 `ValueError` → `None`）、`judge_completion` 把 verdict 挂到 decision 且不泄漏到用户字典、两条端到端（400 拒绝只跑 **1 轮** agent；`APIConnectionError` 仍得到恰好一次额外自检 = 2 轮）。**反向验证**：把 `web.py` 的新分支临时改成 `if False` 后该断言实测失败于 `2 == 1`，证明确实测到了那次浪费的重跑。**真实网络验证**（一次性脚本，不入库）：用错误 api key 打真实网关，`judge_completion` 收到真实 `AuthenticationError: Error code: 401 - invalid_api_key` → `status=unknown` 且 `review_transient=False`（即线上会走短路），错误文本经脱敏后不含密钥；同一脚本换回真实凭据 → `review_transient=None`、评审器正常返回可用结论（`continue`），确认 happy path 未被改动 |

### M8-T5 注记：`git grep -c 'print('` 这一验收口径不可信

路线图标的是「55 → ≤5」。实测本次改动前 `git grep -c 'print(' -- minicc` 求和为 **84**（不是 55），
并且这个数字无法作为门禁，因为它数的是子串出现次数：`event_fingerprint(`、`verification_fingerprint(`
命中 11 处，`minicc/bench_tasks.py` 里嵌在子进程评分脚本字符串中的 `print(` 命中 15 处（那是被写进
`_GRADER` 字符串、由子进程执行的代码，不是 minicc 自己的输出）。把这些一起改会造成真实损坏：上一轮
批量替换确实把 `from .cli_io import cli_out` 注入进了 `_GRADER` 字符串内部。

因此门禁改为 AST 计数的真实 `print()` 调用：`minicc/` 内 **57 → 1**（唯一一处在 `minicc/cli_io.py`，
即刻意保留的 stdout 汇聚点），子串口径同时从 84 降到 26（全部为上述假阳性）。测试
`tests/test_logging.py` 以 AST 断言这一上限，子串值只在文档里留档，不作为通过条件。

### M8-T6 注记：归属判据与四个残留测试

归属判据是**测试实际驱动的 minicc 模块**，不是函数名前缀。例如 `test_agent_service_*` 虽然名字带 agent，
驱动的是任务执行层（`AgentService`/`TaskRecord`/快照），落在 task 文件；
`test_task_snapshot_hides_attachment_payload_and_resume_reloads_it` 驱动会话载荷与续跑，落在 session 文件；
`test_change_request_cannot_be_marked_complete_*` 实际只测完成判定，落在 agent 文件。
唯一一处两可的是 `test_invalid_native_tool_arguments_become_model_feedback`：它同时穿过
`ToolCall.from_openai` 与 `registry.execute`，按「钉住的是 OpenAI 原生调用到内部 ToolCall 的解析边界」
归入 llm 文件。

| 文件 | 测试数 | 主题 |
| --- | --- | --- |
| `tests/test_core_agent.py` | 33 | ReAct 循环、上下文压缩、计划/编排/DAG、完成评估、验证器、系统提示 |
| `tests/test_core_task.py` | 30 | TaskManager/TaskRecord/TaskStore、事件回放与续跑、快照修复、审计导出、`AgentService` 执行 |
| `tests/test_core_tools.py` | 20 | editor/bash/grep/web、注册表与授权、sandbox/MCP/worktree/变更检视 |
| `tests/test_core_llm.py` | 14 | envelope 协议、provider 重试与流式归一化、usage、推理档位 |
| `tests/test_core_session.py` | 8 | SessionStore 往返、多模态载荷、按会话串行、从 checkpoint 恢复 |
| `tests/test_core.py`（残留） | 4 | `minicc.config` 解析（3 条）与离线评测报告（1 条） |

那 4 条刻意**不塞进**五个领域文件：它们与 agent/tools/task/llm/session 都无关，硬归类会让文件名对其内容
说谎，而本任务的目的正是让测试文件可导航。文件头 docstring 已写明这一理由。

失效引用一并说明：`docs/AUDIT_2026-09-20.md:98` 与本文件 `:514` 里的 `tests/test_core.py:1510`、`:35`
是拆分前的行号，对应 `_merge_stream_text` 的测试现在在 `tests/test_core_llm.py`。历史审核文档记录的是
当时事实，不追改行号。

| M8-T8 会话快照读取侧的共享冲突重试（补齐 M3-T7 另一半） | ✅ | M3-T7 只治了写侧：唯一临时文件名 + 跨进程锁 + `_replace_with_retry`。M8-T7 那次全量回归里 `test_concurrent_process_saves_never_corrupt` 在负载下飘红（Windows `[Errno 13] Permission denied`），顺着读代码发现**读侧完全没有同类处理**：`_read_payload`/`load_view`/`save_view`/`_stored_payload_or_none`/`list_sessions` 五处直接 `path.read_text()`，而写侧注释自己就写着「读者不拿锁会让 `os.replace` 撞上 WinError 5」——镜像方向同样成立：写者正在原子替换时，**读者**会在几毫秒内拿到 `PermissionError`。后果分两种，都真实：`load()`/`load_view()` 把它变成用户可见的「无法读取 session …」；`save()` 里那处是 best-effort 吞掉 OSError 的，于是**静默返回 `stored=None`，整批消息 id 被重新生成**（M8-T2 的事件树靠稳定 `m-*` id 定位 fork 点，等于悄悄改掉了用户可见的锚点）；`list_sessions` 给一个正在被替换的会话标「无法读取」。新增 `_read_text_with_retry()`（24 次 × 50ms，与写侧同一量级），五处读全部走它；不改成「读也上锁」：那会把读串行化到写上，且替换本来就是原子的，等待即可 | 新增两条端到端复现前先红：`test_readers_never_surface_a_transient_sharing_violation`（2 写 + 4 读 spawn 子进程各 60 轮压同一文件，修复前**连续 3 次都失败**并打印 `[Errno 13] Permission denied`，修复后连续 3 次全绿）。`_read_text_with_retry` 单测两条：瞬时失败重试到成功（读 4 次拿到内容）、持续失败仍按上限抛出（不变成无限等待）。`tests/test_session_concurrency.py` 3 → 6 条 |

| M8-T9 `/api/chat` 同步路径补上事件词表（M8-T5 的漏网旁路） | ✅ | 发现方式就是「按退出标准做真实端到端」：起 `minicc-web`、`MINICC_LOG_LEVEL=DEBUG`+`MINICC_LOG_FILE`、POST `/api/chat` 跑一个真实只读任务。业务结果全对（回答含目标编号、评审一次判 `complete`、会话落盘、`/api/metrics` 有数），但**日志只有 4 行**：两条 HTTP access + 一条 editor audit + 一条 metrics，agent 侧一条都没有。定位：M8-T5 的事件漏斗在 `task_manager.py:1984` 的 `on_event`（`log_task_event`），工作台 UI 走 `/api/tasks`+SSE 所以词表看起来是全的，而 `webserver.py:557 → AgentService.chat → _chat_locked(on_event=None)` 是同进程旁路；CLI 只在 `main.py:383` 给 `on_trace` 打了个补丁，工具事件同样缺。修法刻意不做「每个 `events.append` 处补一行日志」（十几处、且以后新增事件必漏），而是在 `_chat_locked` 入口把漏斗本身当默认汇：`on_event is None` 时指向 `log_task_event(event, task_id=session_id)`。调用方显式传汇（任务路径）时不替换，因此不会重复记账；一处改动覆盖 tool/trace/decision/review/provider-status 全部事件类型 | `tests/test_logging.py` 22 → 23：`test_sync_chat_path_logs_the_same_vocabulary_as_the_task_path` 用同步 `service.chat()` 跑 fake provider，断言日志含 `provider_retry`/`tool_round_finished`/`run_finished` 与 `task_event task_id=s-chat`、且 api key 与 web token 仍不出现。**先红后绿**：把默认汇换成 `if False and on_event is None` 后该断言实测失败（日志内容为空串）。真实网络复跑同一脚本：日志 4 → 19 行、`tool_round_finished`/`run_finished` 到位、密钥零命中；`provider_retry` 本次没出现是这一趟真的一次都没重试（不是插桩缺失），故该词表仍由 fake-provider 注入故障的那条测试钉住 |

| M8-T10 fork/rewind 不得留下没有结果的工具调用；被丢弃的一次性任务要说话 | ✅ | 发现方式仍是「按退出标准真跑」：M8 退出标准第 1 条要求「10 条消息的会话在第 5 条 fork，两个会话文件独立，`--resume` 能恢复 fork」，于是用真实 CLI 对真实 web 会话（11 条、含工具轮）做一次 fork。会话文件层面的独立性、`forked_from` 血缘、稳定 `m-*` 前缀、源文件摘要不变全部成立——但分支只有 4 条消息，**最后一条是带 `tool_calls` 的 assistant，它的 `tool` 结果被切掉了**。这是 M8-T2 的真实缺口：`fork()` 与 `rewind()` 都直接 `messages[:keep]`，切在一轮工具调用的中间就产出一段模型 API 拒收的历史（`tool_calls` 后必须跟对应 `tool` 结果），分支的第一个请求即失败，而用户看到的只是一个「fork 成功」。修法按「文件里不许存在无效历史」而不是「读的时候打补丁」：新增 `_unsatisfied_tool_calls()` 与 `_keep_through_tool_results()`，把切点向后延到本轮工具结果结束（向后而不是向前，因为结果是用户所选那一轮的一部分），无法修复（结果本来就缺）时立即停止延伸、不追逐、不死循环；`fork`/`rewind` 共用它，`forked_from.from_message_id` 仍记录用户选的点、`keep_messages` 记录真正写入的条数。顺带第二个发现：`minicc --fork-from 3 "任务文本"` 只 fork 就 `return 0`（`main.py:538-553`），任务被静默丢弃，脚本读到的退出码是成功——补 `_warn_unrun_prompt()`，`--fork-from`/`--list-sessions` 带任务时打印「只操作会话文件，本次任务文本没有执行（N 字）」，只报长度不回显内容 | `tests/test_session_fork.py` 测试函数 12 → 18（parametrize 展开后收集 23 条，全绿）。新增：以工具轮为样本的 fork/rewind 不变量（`_unsatisfied_tool_calls(kept) == set()`、角色序列 `system,user,assistant,tool`、血缘仍指用户选的点）、切在完整轮次时**不得**多保留（`kept == 2`）、结果本来就缺失的坏历史不追逐不挂死，以及两条 CLI 断言（带任务时提示「没有执行」且原文不回显、不带任务时保持安静）。**先红后绿**：把 `_keep_through_tool_results` 临时改成直接返回原 `keep`，两条不变量测试同时失败（`assert 3 == 4`）。真实 CLI 复跑同一会话：分支 5 条、以 `tool` 结果收尾、`unsatisfied == set()`、源文件摘要不变 |

| M8-T11 流式合并不再静默丢字符（A 方向：永不丢字 + 连续证据才认累积） | ✅ | 见下方「M8-T11 注记」。`llm/stream_merge.py` 删掉 `accumulate_attempt_text`，改为 `AttemptTextAssembler`（**默认按字节追加**；只有**连续两个片段都是「完整重复前一个片段并且更长」**（`CUMULATIVE_STREAK=2`）才改判为累积快照流；改判那一刻用快照**覆盖**已累积文本，并通过 `latched_now` 让 `openai_provider` 把 `committed_text` 一并**重定基**（rebase），因此交付出去的 `response.content` 是精确快照，只有**流式回调**里可能已经显示了重复）。判定基准刻意用「上一个片段」而不是「已累积缓冲」：增量模式下缓冲可能已经含重复，真快照永远以片段为单位单调增长，因此真累积流必定攒够这条连击、误判只是延后而不是丢失。`openai_provider.py` 每次尝试为 content/reasoning 各持一个 assembler（原来是两个 `str` 局部量） | `tests/test_m1_integrity.py`：M1-T3 的三条 pin 改写并扩到 3 个用例——增量含前缀重复（`"7."+"7.7"→"7.7.7"`、`"def"+"define"→"defdefine"`、`"x="+"x=1"→"x=x=1"`）；真累积 4 段后 `cumulative is True` 且文本恰等于最后一段快照、latch 后继续以快照覆盖；两次前缀重复**不足以**改判（`"a","ab","abc"→"aababc"`）。上一提交留下的 `xfail(strict=True)` 表征测试改为直接断言并删除标记 |

| M8-T12 流一定有关闭路径 + 收尾噪声不再进 stderr | ✅ | 真实 CLI 流式跑完，答案正确、`rc=0`，stderr 仍打印 `an error occurred during closing of asynchronous generator … GeneratorExit → RuntimeError: generator didn't stop after athrow()`（`httpcore2/_utils.safe_async_iterate`）。代码侧确实有两处该关不关：chat_completions 循环**只在 `except` 分支 `aclose()`**，成功交付那条出口从不关；responses 的 `_attempt()` 任何分支都不关。新增 `_close_stream()`（`aclose` 优先、退回 async `close`——SDK 的 `AsyncStream` **根本没有 `aclose`**，第一版助手因此静默空转，是测试替身骗了我一次），并把关闭挪到 `finally`，同时关闭 `stream.__aiter__()` 造出来的那层异步生成器。**但真机复跑 3/3 仍然打出同一段 traceback**：泄漏体是 httpx 连接层的 `HTTP11ConnectionByteStream.__aiter__`，不在我们持有的这两个对象上（很可能属于某次非流式请求的 response 或 SDK 内部再包一层）。**这条按未修复保留**，只把「该关必关」的代码债还掉。**第三段修复才结案**：`logging_setup.quiet_loop_teardown()` 把 `loop.call_exception_handler` 里这类「异步生成器关闭失败」事件改道到 DEBUG 日志（其余事件仍原样交给默认处理器），在 CLI 与 web 的三处 `asyncio.run` 协程入口与 subagent 线程入口安装。真机复跑：泄漏体在补完关闭后已从 `HTTP11ConnectionByteStream` 移到 `PoolByteStream`（1501B），改道生效后 **4/4 次流式真机运行 `stderr` 为 0 字节**、答案正确、`rc=0`，且 DEBUG 日志里 9 行词表齐全却 `loop_teardown` 命中 0 次——说明这次是真的不再产生该事件，而不是被吞掉；即便上游再次产生，用户看到的也只是一条日志而不是一段崩溃栈 | `tests/test_core_llm.py` 14 → 16：`_WatchedStream` 严格照 `AsyncStream` 的形状做替身（`__aiter__` 是异步生成器函数、只有 async `close()`），断言干净交付与中途 `StreamProtocolError` 两条出口都`stream.closed and iterators_closed == 1`。先红后绿：把 `finally` 里传入的对象换成 `None` 两条同时失败。**真机部分未达成**：同一 CLI 命令 `stderr` 仍稳定 1438 字节，（该行的「真机未达成」结论以上一段为准：噪声已在第三步消除） |

> **事后更正（同日稍晚，M8-T12/T13 期间查清）**：上面那句归因**只对了一半**。真正在终端里少掉尾巴的不是
> 合并层——落盘的会话内容一直是完整的 `7.7.7`。用 `visible_stream_check.py` 连跑 3 次，CLI 打印分别是
> `7.7`、`7.7.`、`7.7`，而三个会话文件里存的都是 `7.7.7`：**少的是显示层**（见文末 M8-T13）。
> 本节记录的 `accumulate_attempt_text` 缺陷本身仍然成立，它的证据是上表那三行离线可复现的合并结果与
> `test_m1_integrity`/`test_core_llm` 的断言，不是那次终端显示。教训写下来：**用终端输出给模型链路定罪，
> 一定要先比对落盘的会话内容**，否则会把显示层的 bug 记账到合并层头上（本文件此前就这么错过一次）。
> 另外，M8-T11 的 latch 当时会**吞掉**可见增量（rebase 后不再发 suffix），真机复跑才暴露；已改为「照样发
> suffix、只把缓冲重定基到快照」，`deltas == ["aa","aab","c"]` + `content == "aabc"` 钉住这个形状。
| M8-T13 CLI 可见输出必须等于落盘答案（已修，两层各占一半） | ✅ | 真机 3/3 复现「终端打印 `7.7`/`7.7.`，会话文件里存的是 `7.7.7`」后分两层定位。**第一层（数据）**：`agent/loop.py:_merge_incremental_text` 对**增量**片段跑了完整的累积折叠——`previous.startswith(current)` 直接返回 `("", drop)`，于是 `"7",".","7"` 的第三个 `7` 被丢掉（离线可复现：旧规则把 `7.7.7` 只发出 `7.`）。规则收窄成**只吸收「完整重复已累积前缀并且更长」这一种**，其余一律原样追加，`test_agent_loop_deduplicates_cumulative_public_stream_updates` 的 `["aa","b","c"]` 旧契约与新用例同时通过（第一次尝试是整层删除折叠，被这条既有契约挡下——它对应的是 provider 直接吐累积块的路径，不能顺手拆）。**第二层（显示）**：`main.py:395` 只要 `writer.started` 就**无条件**不打印最终答案，所以流式一旦短一截，屏幕上的错答案就永久留着、而落盘内容是对的。`StreamWriter` 现在记住自己写过什么并暴露 `matches()`，只在「看到的 == 落盘答案」时才省略最终打印。**M8-T12 仍未结案**：修完这两层后真机 `visible == stored` 3/3 成立，但 stderr 仍有 1501 字节的 httpcore 关闭栈，泄漏体从 `HTTP11ConnectionByteStream` 变成更内层的 `PoolByteStream`（说明我们持有的两层已经关对了，剩下的在 httpx/httpcore 内部） | `tests/test_m1_integrity.py` 13 → 15：`test_m1t3_stream_deltas_reach_the_surface_verbatim`（假 provider 逐段 `"7",".","7",".","7"`，断言 `"".join(on_stream) == result.answer == "7.7.7"`）与 `test_stream_writer_knows_when_the_screen_fell_short`（短流不得抑制最终打印、补齐后不得重复打印、尾部空白不算差异）。旧契约 `test_agent_loop_deduplicates_cumulative_public_stream_updates` 保持绿色。**真机验收门**：`visible_stream_check.py` 的 `RESULT visible-equals-stored` 从 0/3 变成 **3/3**（同一 workspace、同一问句、3 次独立进程）。全量 `.venv` **879 passed** |

### M1-M3 退出标准真跑记录（第一批，2026-09-22）

按第三节原文逐条执行，不走附录 D 的自评：

| 标准 | 结论 | 证据 |
| --- | --- | --- |
| M1-1 `pytest -q` 全绿 | ✅（Windows 这条腿） | `.venv` 全量 **880 passed**；Ubuntu 那条腿本机不可用，只有 CI 能证，**不在此声明** |
| M1-2 `scripts/reliability_probe.py` 一键复现、退出码 0 | ✅ | 真跑：9 个 M1 target 全绿，`exit=0` |
| M1-3 人工核查（只认 text delta 与 `[DONE]`、空答案不算成功） | 未复核 | 需要逐行读协议分支，本批未做 |
| M1-4 golden delta 序列：streamed text 必须与 answer 一致 | ✅（今天才真正成立） | 判据落在 M8-T13 的两条新测试（增量逐字到达 surface；`StreamWriter.matches`）+ `visible-equals-stored` 真机 3/3。**此前这条标准是靠终端肉眼看的**，实际一直在丢字 |
| M2-1 / M2-2 四份安全测试文件全绿 | ✅ | `test_web_security + test_permission_modes + test_allowlist + test_file_tree_api + test_security_perimeter + test_task_durability` 共 **63 passed** |
| M3-1 Origin/CSRF 与会话持久化全绿 | ✅ | 同上（含 `test_web_security`、`test_task_durability`） |
| M3-3 `grep -rn sk-` 在 `.minicc/` 与日志里零命中 | ❌ **标准本身不成立** | 仓库自身 `.minicc/web-8765.stdout.log` 命中 **19,167 次**，全部是 **`task-<hex>` 里含子串 `sk-`**（真实密钥字符串不在其中、文件 gitignored 且 mtime 早于 M1 开工一个月）。和 M8-T5 的 `git grep -c 'print('` 同一类：**字面 grep 口径不可信**。 |

M3-3 的处理不是把标准删掉，而是把它变成可执行、可证伪的门：`scripts/reliability_probe.py` 现在多跑一段
`scan_credentials()`，只认真正的凭据形状（`sk-[A-Za-z0-9_-]{20,}`、AKIA、PEM 头、`.env` 里那把 key 的原文），
**只报文件路径与规则名、绝不打印命中内容**（PEM 字面量在脚本里拼接，避免本仓库自己的 pre-commit 钩子把它当泄漏）。
验证：真实状态目录 0 命中 `exit=0`；把一条长 `sk-…` 和一条 `AKIA…` 放进临时目录后 **2 命中、`exit=1`**（先红后绿做完再删临时文件）。
### M4 退出标准真跑记录（第二批，2026-09-22）—— 含一条**未达成**

| 标准 | 结论 | 证据 |
| --- | --- | --- |
| M4-4 `benchmarks --suite v2` 的 `grading_coverage=1.0`、分母 ≥24、edit 类 ≥10 | ✅ | 真跑 `--suite v2`（不 `--run`）：`fixture_count=24`、`grading_coverage=1.0`、按类 `write 12 / multi-file 6 / test-fix 6`（edit 类 12 ≥10）；`pass_at_1=None`（未运行，符合「not_run 既不算通过也不算失败」的注记） |
| M4-5 A/B gate 违规时 exit code 1 | ✅ | 同一份结果 `--gate pass_at_1>=0.5 --gate grading_coverage>=1.0` → **exit 0**；把 variant 换成未运行那份（`pass_at_1=None`）→ **exit 1 + `[GATE FAILED] pass_at_1>=0.5 实际=None`**。两个方向都验；且它把 None 当 None（`不可计算（None，而非 0）`），不拿 0 冒充结论 |
| M4-6 未知模型 `cost_usd=None` 且 `cost_available` 如实 | ✅（真机 2 条） | `--run --max-tasks 2` 真跑：`cost_available=0`、逐任务 `cost_usd=None`、`token_usage_available=2`，同时 `latency_p50_ms=66695.5 / p95=120182.05 / tokens_per_success=179683` 都有值 |
| M4-7 `pytest -q -W error` 全绿 | ❌ **未达成** | `python -m pytest tests/ -q -W error` → **2 failed, 878 passed**：`tests/test_task_worker.py::test_manager_process_mode_runs_task_in_subprocess`、`::test_worker_survives_host_restart_and_continues_long_stream`，均为 `ResourceWarning: subprocess NNNN is still running`（`subprocess.Popen.__del__` 经 pytest 的 unraisable hook 升级为错误）。同一条标准还要求「PR 门禁 ≤15 分钟」——实测 178s ✅，所以**只有 `-W error` 这半条没过**；附录 D 把 M4 记为已落地，这一项与该记录不符 |
| M4-2 `npm run test:web` 离线基线 | 未复核 | `test:web = node tests/web_smoke.mjs`（`node_modules` 已在），本批未跑，排下一批 |
| M4-1 证据链回归 / M4-3 `/api/*` 覆盖与 rpc ≥10 method | 未复核 | 下一批 |

`-W error` 那条失败的性质（下一步要定的设计问题，不是简单的测试脏）：`task_manager.py:1824-1826` 的
`_monitor_worker` 在 `self._closing` 时直接 `raise WorkerDetached()`，**既不 terminate 也不保留 `Popen` 引用**，
于是子进程活着而句柄被 GC → `ResourceWarning`。这正是「宿主关闭时把 worker 脱管交给 auto-resume」的既定语义，
但实现上留下两个后果：(1) 解释器关闭期抛 unraisable 警告（任何开 `-W error` 的门禁都会红）；
(2) 关掉宿主真的会留下孤儿进程。修法有两种、语义不同，需要产品决策：**A** 关闭时先写 cancel 标志、有界等待
（例如 ≤5s）后再 terminate，把「脱管」限定给真正的崩溃恢复；**B** 保留 `self._worker_processes` 注册表并在
shutdown 末尾统一 reap（不改变「让它继续跑完」的语义，只消掉警告与句柄泄漏）。A 改变可观察行为（正在跑的任务
会被中止），B 不改。
### M8-T7 注记：一次真实失败的时间线，以及「不给结论」的边界

一次真实只读小任务消耗 118,499 tokens、跑了 5 轮 `run_agent` 后才以 provider `451 censorship_blocked` 失败。
**根因经日志逐条复核，与最初记录的原因不同**：不是任务级恢复重放了不可重试错误（`web.py` 的恢复分支只在
`is_transient_failure` 为真时才重跑，451 不在 `_RETRYABLE` 名单里，该分支没有触发）。实际时间线是：
06:02:44 第 1 轮 agent → 06:02:51 完成评估返回 `completion_unknown`（评审器自己的模型调用被网关拦截）→
`completion_judge_retry` **重跑整轮 agent**（第 2 轮）→ 第 2/3/4 轮的评审连续返回 `completion_continue`
「仍有目标未满足」，每次又是一整轮 agent 重跑 → 第 5 轮的模型请求直接被 451 拦掉。也就是说：**评审器侧的
基础设施故障被当成「任务没完成」处理，代价是整轮 agent 重跑**，而内容一旦被网关拦截，重跑不可能改变结论，
只会把不断变长的上下文再送 4 次。仓库里已有同类判断的先例——`llm/openai_provider.py::StreamProtocolError`
的注释写明「重放会重发全部上下文与工具 schema，必须 fail fast」。

判据边界比修复本身更重要，三点记录在案：

1. **`False` 只用于「这个请求被按策略拒绝」**。判定用异常对象而不是错误字符串：`APIError`（含 `APIStatusError`
   的 4xx/5xx 与连接类）和 `httpx.HTTPError` 之外的异常一律返回 `None`。`RuntimeError("Anthropic HTTP 451…")`
   走的是 Anthropic 自己的错误类型，不经过这条 HTTP 栈，因此**不越权给结论**，保持原有的有界自检——它也许
   应该被判为 `False`，但没验证过的推断不会变成新的失控 break。
2. **`None` 与 `True` 共用原来那条路**：评审器答了但结论不可用（缺 evidence、字段类型错）仍是「要求 agent
   再自检一次」，这是有效语义——agent 换一版答案，评审器就可能换一份结论。只有请求本身被确定性拒绝才短路。
3. **保守结论不变**：评审器不可用时依然不允许宣称完成（`任务未完成：完成评估请求被模型端拒绝…`），省下的
   是那一次整轮重跑，而不是安全边界。文案以「完成评估」开头是有意的：`web.py` 用这个前缀识别
   `judge_unavailable` 并把 `ignore_result_error` 传给完成守卫，改掉前缀会让守卫覆盖掉真实原因。

### 尚未开始

路线图 M1..M8 的任务至此全部落地并有逐项验证记录（M8-T7..T12 六条由真实运行与真实失败驱动的附带修复在内）。
M6-T4/M6-T5 的落地记录来自 `02059ea`、`a97bf13` 等一批提交（对应 `tests/test_background_shell.py`、
`tests/test_parallel_writes.py`），本日志未逐条复核，暂不代为背书；下一步是按第三节各里程碑的**退出标准**
（`## 三` 里每个里程碑自带的检查清单）加上第六节的跟踪指标做一次整体复核（含真实模型端到端），而不是继续
加功能。注：本文件没有「第八节」，此前此处写的「第八节退出标准」是错的交叉引用——退出标准按里程碑分散在
第三节（`:44/:88/:131/:178/:229/:269/:302/:335`），一次性列在总表 `:23` 的「退出标准」列。


### M8-T11 注记：为什么改成「宁可重复，绝不丢字」

复核 M8 退出标准第 2 条（长期记忆跨任务召回）时，记忆写入与召回都正常，但终端上打印的最终答复是
`7.7`，而记忆里明明写着 `7.7.7`。先排除脱敏（`redact_text("…7.7.7")` 原样返回、未标记为命中），线索指向
`llm/stream_merge.py`：
`accumulate_attempt_text` 用 `fragment.startswith(attempt)` 猜「这个网关发的是累积快照」，猜中就丢弃重叠前缀。
对**真累积快照**那是对的呢条（`tests/test_m1_integrity.py:72` 就钉着 `("aa","aab") -> ("aab","b")`），但对
**恰好重复已累积前缀的增量片段**它是静默丢字符：

| 增量片段序列 | 现在合并成 | 应为 |
| --- | --- | --- |
| `"7."`, `"7.7"` | `7.7` | `7.7.7` |
| `"def"`, `"define"` | `define` | `defdefine` |
| `"x="`, `"x=1"` | `x=1` | `x=x=1` |

这正是该模块 docstring 自己写的 P0-1（重叠去重污染 `write_file`/`bash` 参数）同一类后果，只是换了触发条件；
而这两种解释在**单个片段上原理上不可区分**，所以必须选一个方向承担代价：

- **A：默认按字节追加，连续多次证据才切到累积模式**。代价是累积型网关最坏情况下**重复**输出（用户看得见、
  可事后修），换取永不静默丢字；要改 `tests/test_m1_integrity.py:72` 的既有契约。
- **B：保持现状，但累积识别只在显式开关下启用**。代价是未被开关覆盖的兼容网关回到重复，改动面最小。

不选「加长度阈值」这类第三条：`"def"/"define"` 与真快照在长度上不可分，只是把误判换个尺寸而已。
**已按 A 落地**（用户选定方向：永不静默丢字，代价换成看得见的重复）。实现要点与残余风险：

1. `AttemptTextAssembler` 默认按字节追加；改判累积需要**连续 3 个**「完整重复前一片段且更长」的片段，
   判据比较的是**上一个片段**而不是已累积缓冲（增量模式下缓冲可能已含重复，真快照永远以片段为单位增长，
   所以真累积流一定攒得够这条连击——误判只会延后，不会漏判）。
2. 改判那一刻用快照**覆盖**缓冲，并让 provider 把 `committed_text` 重定基到该快照；此后每个快照直接替换。因此
   真累积网关的**交付文本依旧精确**，代价只在流式回调里可能已经把前几段重复渲染过一次（可见、可事后修）。
   阈值取 2 而不是 3 是因为确实存在只有三段快照的累积流（`tests/test_core_llm.py` 钉着的
   `"aa","aab","aabc"`）——阈值 3 对它永远攒不够证据，会把最终文本弄脏。
3. 残余风险方向相反且很小：增量流若恰好连来 2 个「完整重复前一片段并增长」的片段会被改判为累积、在重定基时丢字。
   真实增量协议的片段互不重叠，这类连击概率远低于旧写法在**单个**片段上就误判的概率——这正是本次改动
   要买到的东西。
4. 上一提交那个 `xfail(strict=True)` 表征测试已按约定删除标记、改成直接断言（`tests/test_m1_integrity.py`
   M1-T3 共 3 个用例：单片段前缀重复仍是增量、真累积被识别并自正、一次重复不足以改判）。被**故意改掉**的旧
   契约有两条、都不是回归：`accumulate_attempt_text("aa","aab") -> ("aab","b")`（单片段前缀猜，正是丢字的根源）
   随该函数一起删除；`test_provider_deduplicates_cumulative_stream_chunks` 的 `deltas == ["aa","b","c"]` 改为
   `["aa","aab"]` 并保留 `content == "aabc"`，把「流式可见重复、交付文本精确」直接写进断言。


### M8-T13 已修：判据留下，别再拿终端输出给合并层定罪

判据保留在这里，因为它比这次的结论更长寿：**可见输出必须等于落盘内容**，回归门是
`visible_stream_check.py` 的 `RESULT visible-equals-stored`（修之前 0/3，修之后 3/3）。
两条过程教训也留在案上：

1. 一开始我把「终端显示 `7.7`」直接归罪给 `llm/stream_merge` 的累积启发式并据此改了那层。合并层的缺陷
   本身是真的（离线三行证据 + 单测钉住），但**那次终端现象不是它造成的**——落盘内容一直是对的。以后先比对
   落盘会话内容，再决定给哪一层记账。
2. 真正在丢字的是 `agent/loop.py` 里**第二份**同样的折叠逻辑。同一类启发式在两个层各写一遍，就要在两个层
   各判一次代价；`stream_merge` 的收口当时没有覆盖到 loop 这份，这是「单点实现」名义下的漏网。
