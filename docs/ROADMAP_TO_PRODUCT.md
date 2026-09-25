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
  验收：`tests/test_m1_integrity.py::test_m1t1_recovery_required_does_not_loop_on_plain_text`——FakeProvider 恒定返回纯文本且 `require_recovery_inspection=True`，断言 `STAGNATION_REPLAN_LIMIT` 次后以 error 结束、总 turn ≤5，并用 `asyncio.wait_for(20)` 确保不挂死。

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
  验收：`--suite v2`（不带 `--run`）输出 `grading_coverage=1.0`、pass@1 分母 ≥24；新增 ≥20 条可写任务（≥8 条真写文件、4 条跑测试修 bug、4 条多文件）；`tests/test_bench_tasks.py` 校验 schema、id 唯一、fixture 路径不逃逸、grader 类型白名单、`max_minutes` 为正，并用 fake provider 跑 2 条 file_contract fixture 断言一过一败（验证 grader 不恒真）；`test_grader_unreadable_by_file_tools` 断言 `read_file/grep/glob/tree` 读 `.graders` 全部返回 TOOL_ERROR；手动跑 2–3 条真实模型 edit fixture，输出含 verification 事件与 completion 判定，且工作区外无任何写入（`git status` 校验隔离目录干净）。

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
| M1-T5 缺 finish_reason 整段重放 | ✅ | 新增 `StreamProtocolError`（`openai_provider.py:166`），`_is_stream_retryable` 对它返回 False；`"stream ended before completion"` 从可重试子串列表移除 | `test_m1t5_stream_without_finish_reason_fails_fast`。**口径修正（第五批复核时发现的表述不准）**：这里写的「断言只发 1 次请求」数的是被打桩的 `provider._create` 调用次数，不是真实 HTTP 请求数——它证明的是「我们这一层没有重放」，不证明网关侧只收到一次。真 HTTP 计数由 `test_m1t3_delta_only_gateway_costs_one_request_and_errors` 用 `MockTransport` 钉住（恰好 1 次） |
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
| M4-T1 先修证据链 | ✅ | 四处修复：(1) `tool_policy.py` 新增 `command_may_modify_workspace` / `is_workspace_write` 与 `WRITE_TOOL_NAMES`，`loop.py` 三处写判定与 `web.py::on_tool` 的 `write` 标志改用 `is_workspace_write`，`sed -i` / `python patch.py` / 重定向 / `git checkout` 等 bash 改写现在会触发 `verification_required`；(2) `verification_plan.py` 指纹 suffixes 补 `.md/.sh/.ps1/.svg/.png` 等并把无扩展名文件（Makefile/Dockerfile）纳入扫描，改这些文件不再复用旧通过缓存；(3) `completion.py::_enforce_completion_evidence` 区分 `packet_ids`（防幻觉）与 `citable_ids`（write/verification/error/真实 tool），完成判定必须至少引用一条真实证据，零工具只读任务无法只用 trace id 判 complete；(4) `_evidence_packet` 改为"保留最早 40 条重要事件 + 最新若干"配额，100 个 write 事件下 `event-1` 仍可被引用（旧的优先排序只保留最新 write 会逐出最早证据）。附带：`web.py::emit_node_event` 把只读 DAG 节点的 `kind=="tool"` 事件并入主 `events`，否则 planner 只读计划在判定器眼里像零工具会话；`config.py::normalize_model_name` 空串值回退默认（与 `normalize_reasoning_effort` 一致），修复 resume 旧任务记录无 model 时崩溃；(5) 对齐退出标准 2「正常 fake provider 下断言含至少一次工具证据」——`minicc/llm/fake.py::FakeProvider` 首个 agent 轮发一次只读 `tree` 调用、判定轮用新增 `_select_citable_evidence`（按完整 marker 定位用户消息里的证据包，镜像 `_is_citable_evidence` 选可引用 id，避免误匹配含「执行证据」字样的系统提示词），`tests/test_benchmark_runner.py` 的本地 fake 同步改造并复用该选择器；`tests/test_task_worker.py::test_worker_survives_host_crash_and_continues_long_stream`（M4-T1 时该名不带 crash_and_continues_long_stream，M8-T14 换的名） 的 `started_file` 断言由 `["started"]` 改为 `["started","started"]`（两轮 agent 调用，仍能证明 worker 未被重启复制） | `tests/test_m4_evidence_chain.py`（4 条命名回归，先红后绿）；`tests/test_core.py` 全绿（含重写的 `test_agent_service_preflights_complex_tasks_with_a_safe_model_plan`——原 fake agent 从不调用工具、靠 trace id 判完成，正是本任务要消灭的缺陷语义，按 A.3-2 重写为真调用 `read_file`）；`tests/test_task_worker.py`（5 条）、`tests/test_benchmark_runner.py`（15 条）、`tests/test_auto_resume.py`、`tests/test_subagent_task.py`、`tests/test_permission_modes.py` 全绿；`scripts/reliability_probe.py` exit 0 |
| M4-T3 Web HTTP 面 + RPC 的 Python 测试 | ✅ | 新增 `tests/test_http_surface.py`（56 条），起真实 `ThreadingHTTPServer` + 真实 `AgentService`（fake provider，无网络）用 `urllib` 打真实请求，补齐此前 `grep api/tasks tests/*.py` 为 0 命中的空白：(1) 每个 POST `/api/*` 路由至少一条——`/api/tasks`(202+`_defer_schedule`)、`/api/tasks/batch`、`/api/tasks/{id}/cancel`+`/resume`(404)、`/api/chat`(200 含 `fake-provider-answer`)、`/api/workspace/select`、`/api/allowlist`、`/api/sessions/rewind`、`/api/workspace/restore`、`/api/worktrees`+`/remove`(git init，201/200)、未知路由 404；(2) 传输层状态码——畸形 JSON 400、空体 400、`WebAuth(required=True)` 缺 token 401→带 Bearer 202、跨站 `Origin` 状态变更 403；(3) `workspace_roots` 白名单在 task/batch/select/chat/rpc.turn-start 五个入口越界均 400（rpc 为 HTTP 200 + body error code -32602）且含「白名单」；(4) 8 线程并发 submit 全 202 且 task_id 唯一；(5) `rpc.py` 分发器 ≥10 个 method 独立单测（参数化 m0..m9）+ initialize/未知 method(-32601)/非法请求/缺 jsonrpc 版本/method 类型/id 类型/params 非对象/通知返回 None/通知错误抑制/ValueError(-32602)/KeyError(-32004)/通用异常(-32000)/非 Mapping 返回/batch/空 batch/`parse_request` strip；(6) `/api/rpc` HTTP 集成——initialize+thread 往返、turn 生命周期(start→read→interrupt)、未知 method 与缺 task、非对象 body 400、通知 204。**测试自身缺陷修正**：`workspace_select` 返回 posix 路径，断言改用 `Path(...)==Path(...).resolve()` 归一化 Windows 斜杠；`rewind` 的 `keep_messages` 须 ≥1（0 触发 `SessionError`），断言改查响应 `kept` 键（rewind 不回显 session_id）。为把 56 条压进 20s，`serve_forever` 用 `poll_interval=0.05`（默认 0.5s，每个 server 关停各等一个轮询周期，~30 个短命 server 累计 ~13s） | `pytest tests/test_http_surface.py -q` 56 passed in 8.20s（< 20s） |
| M4-T4 价格表与美元成本核算 | ✅ | 新增 `minicc/pricing.py`：`ModelPrice`（USD/1M tokens 的 input/output/cache_read/cache_write 四价）、`DEFAULT_PRICE_TABLE`（仅收录公开标价的 gpt-4o/4o-mini/4.1/o1/o3、claude-3-5/3-7-sonnet、3-5-haiku、opus-4；虚构默认模型 `gpt-5.6-terra` **故意不收录**）、`price_for`（大小写不敏感**最长前缀**匹配，`gpt-4o-mini` 不会被 `gpt-4o` 误价）、`cost_usd`（`prompt_tokens` 视为 hit+miss 总量，hit 部分按 cache_read 折扣价、miss 按 input 价、cache_write 单列、completion 按 output 价；**未知模型返回 None 而非 0**，区分「免费」与「无价」）、`load_price_table`（合并 `MINICC_PRICING_JSON` 运行时覆盖，畸形条目静默忽略不抛）。接线：`benchmarks.py` 每行 result 落 `cost_usd`（report 的 `cost_per_success_usd`/`cost_available` 此前已消费该字段，现终于非空）；`task_manager.py` 两处 `snapshot()`（完整 + summary_only）落 `cost_usd`；`main.py` REPL 新增 `/cost`（跨轮累计 `tokens_used`，无价模型显式提示）；`web/src/panels/index.js::taskMetrics` 在 `cost_usd` 为数字时追加 `$` 段（已 `npm run build:web` 重新打包，`check:web` 通过）。`llm/fake.py` 三种响应补确定性 `usage`（prompt/completion 拆分），使成本链路无需真实模型即可观测。**附带修复**：`tests/test_task_durability.py::test_readonly_task_starts_without_copying_workspace_snapshot` 的 stub config 缺 `model` 字段，在前序会话给 `submit()` 加 `normalize_model_name` 后一直 400（与本任务无关的既有红），补 `model="test-model"` | `tests/test_pricing.py`（13 条）：固定 usage `cost_usd` 精确到 1e-6、未知模型 None、最长前缀、cache hit 折扣价、cache_write 单列、env 覆盖、畸形覆盖忽略、负计数钳零、fake provider + 显式单价跑 1 条任务后 `cost_per_success_usd` 非 None 且 >0、results.json 与 task snapshot 均不含 api_key；回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_task_durability`(9)、`test_task_worker`、`test_m4_evidence_chain`、`test_auto_resume`、`test_subagent_task`、`test_permission_modes`、`test_core`、`test_p0_p1_p2`、`test_http_surface`(56)；`reliability_probe` exit 0；fake provider 服务器下 `node tests/web_smoke.mjs` exit 0 |
| M4-T5 fixture 工作区 + edit fixture + hidden grader | ✅ | 新增 `benchmarks/tasks.v2.json`（24 条可写任务：write 12 / test-fix 6 / multi-file 6，file_contract 17 + command_contract 7，全部带 `fixture` 与正数 `max_minutes`）；新增 `minicc/bench_tasks.py`：`v2_tasks`/`validate_task`（必填键、id 唯一、fixture 路径逃逸拦截、grader 类型白名单、max_minutes>0）、`resolve_grader_dir`（显式参数 → `MINICC_EVAL_GRADER_DIR` → 仓库**外**同级 `.graders`，默认不落仓库内）、两类隐藏 grader 驱动脚本（`file_contract`：exists/contains/not_contains/equals/regex/json_equals；`command_contract`：`{python}` 占位符替换 + 期望退出码/stdout marker，并以 `PYTHONDONTWRITEBYTECODE=1` 跑命令避免 Windows 同 mtime 陈旧 .pyc 掩盖修复）、`grade_v2` 分发（签名对齐 `grade_behavior`）。`benchmarks.py`：`--suite v2`（加载即逐条 `validate_task`，失败 `parser.error`）、`--grader-dir`、`run_benchmark(grader_dir=...)`，grading 段按 grader 类型路由到 `grade_v2`；`build_report` 在无执行行时把 `grading_coverage` 回退为**定义级**覆盖率（声明 grader/verify_command 的任务占比）并新增 `gradable_task_count`，使 `--suite v2`（不带 `--run`）即可输出 coverage=1.0、分母≥24 而不烧模型。`tools/fs.py`：`.graders` 入 `SKIP_DIRS`（glob/grep/tree 递归不可见）+ `_reject_grader_dir` 在 read_file/write_file/edit_file/glob/grep/tree 直接命中 `.graders` 时抛 `ToolError`→`[TOOL_ERROR]`。**前提修正**：roadmap 列的 `benchmarks/fixture-workspaces/` 未单独建——v2 fixture 沿用既有 `prepare_fixture` 的内联 `fixture` 字典 + 独立 tempdir 机制（M4-T5「改什么」已确认隔离已存在），再建一份磁盘种子树只会与 tasks.v2.json 内容重复并引入漂移，故合成仓库以内联 fixture 表达 | `tests/test_bench_tasks.py`（12 条）：schema/id 唯一/≥24/类别下限、定义级 coverage=1.0 且分母≥24、fixture 逃逸/未知 grader/max_minutes≤0 均 `validate_task` 抛错、`resolve_grader_dir` 优先级且默认在仓库外、file_contract 种子态一过一败、json_equals+not_contains 判别、command_contract 修 bug 前后判别（独立工作区避 .pyc 竞态）、**fake provider 跑 2 条 file_contract 断言一过一败**、`read_file/grep/glob/tree` 打 `.graders` 全 `[TOOL_ERROR]`、递归 tree/glob/grep 不泄露 `.graders`/SECRET。`--suite v2`（无 --run）实测 `grading_coverage=1.0 gradable_task_count=24 pass_at_1=None`。**真实模型手动跑 2 条 edit fixture**（step-3.7-flash）：`v2-fix-add` completion.status=complete、含 `verification_required/observed/passed`+`completion_complete` 事件、4 次 write、command_contract grade passed=True；`v2-greeting-needs-fix` 触发上游 429（RPM 10）但已写入并 file_contract passed=True；两次运行后仓库 `git status --porcelain` 新增条目为 (none)，确认工作区外零写入。回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_pricing`(13)、`test_core`、`test_m4_evidence_chain`、`test_todo_tool`、`test_task_worker`、`test_web_security` |
| M4-T6 A/B 对比器与统计门槛 | ✅ | 新增 `minicc/bench_compare.py`：两份 `build_report` JSON（或裸 `results` 数组）逐任务对齐（共有 task_id 求交，独有任务进 `baseline_only_task_ids`/`variant_only_task_ids` 并出 note，绝不静默丢弃），输出 (1) pass@1 差值 + 每版 **Wilson 95% 得分区间**（小样本/极端比例仍落 [0,1]）+ 差值的 **Newcombe 混合得分区间**；(2) per-success cost 差值 + **配对 bootstrap 95% CI**（按 task_id 有放回重采样保配对，`random.Random(seed)` 确定性，默认 2000 次）；(3) latency P50/P95 差值（R-7 插值，与 `build_report._quantile` 同算法，本地实现避免与 `benchmarks` 循环导入）；(4) 按 category 分解的 pass@1 base/var/delta。`parse_gate` 解析 `metric>=|<=|>|<value`，仅认 `pass_at_1`/`cost_per_success_usd`/`latency_p95_ms`/`grading_coverage` 四类，对 **variant** 指标判定，指标为 None 时 **fail-closed**（视为违反，不可用 ≠ 达标）；任一违反 `main()` 返回 1 并打印 `[GATE FAILED]`。`--repeat N`：N<10 按路线图**不下 pass@k 结论**（仅出 note），N≥10 还需报告每任务携带 ≥N 次 `draws` 才用无偏估计 `1-C(n-c,k)/C(n,k)`（log 空间防溢出）计算，否则 note 说明无法计算。`--json-out`/`--junit-out`（每 gate 一 testcase，违反写 `<failure>`，XML 转义）。`render_delta_table` 输出人工可读 markdown delta 表。`benchmarks.py::main` 新增 `compare` 子命令派发（`raw[0]=="compare"` → 懒导入 `bench_compare.main(raw[1:])`，避免循环导入且不与报告解析器 flag 冲突），故 `python -m minicc.benchmarks compare --baseline a.json --variant b.json` 直接可用 | `tests/test_bench_compare.py`（22 条，先红后绿——首版 `_VAR_FLAGS` 误写 8/12 即被 `pass_at_1==0.75` 断言抓出）：Wilson 与独立闭式 `_ref_wilson` 逐项吻合到 1e-12、边界 0/0→None·0/5·5/5·越界抛错、Newcombe 与 `_ref_newcombe` 吻合、12 任务两版（6/12 vs 9/12）delta=0.25 且 CI 含真值、cost 差值精确 + bootstrap CI lo≤hi、P50/P95 差值与手算 `_ref_quantile` 吻合（variant 更快→负）、category 分解 delta 自洽、任务集不对齐出 note 且对齐数=11、无可评分行→delta=None（非 0）+note、repeat=3 不下 pass@k、repeat=10 无 draws 不下结论、带 draws 的 pass@k=1-11/66 与 1.0、`parse_gate` 各形态 + 未知指标/缺比较符/非数抛错、gate fail-closed、**`main()` gate 违反返回 1（pass_at_1>=0.9 对 0.75 必红）/ 满足返回 0**、写 json+junit、坏 gate/repeat<1 `SystemExit`、delta 表人工可读、junit 转义与失败计数、`benchmarks.main(["compare",...])` 派发。CLI 实跑：gate 满足 exit 0（delta 表含 pass@1 0.5→0.75、cost 0.02→0.0107、write 类 0.5→1.0）、gate `pass_at_1>=0.99` exit 1。回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_bench_tasks`(12)、`test_pricing`(13)、`test_core` |
| M4-T7 检索决策门（hit-rate 基线） | ✅ | 新增 `benchmarks/retrieval-hitrate.json`（`schema_version=retrieval-1`，20 条「已知答案定位」case：每条 = 开发者中英混合提问 + 应答的仓库相对文件 `targets`，全部经核实存在，覆盖 pricing/bench_compare/bench_tasks/retrieval/fs/registry/web/task_manager/mcp/config/fake/completion/verification_plan/tool_policy/loop/rpc/session/bash/editor/usage）；`benchmarks.py` 新增 `load_retrieval_cases`（校验对象/非空/id 唯一/非空 query/targets 为非空且不逃逸的相对路径列表/ks 为 ≥1 整数）、`evaluate_retrieval`（建一次 `LocalEvidenceIndex`，逐 case `search(query, limit=max(ks))`，`recall@k=|targets∩top-k|/|targets|` 按 case 求均值、MRR 取首命中排名倒数、附带 `hit@k` 与 per-case `first_relevant_rank`/`top`）、`retrieval_decision`（recall@5<0.6→建议评估本地 embedding 且须附 A/B；≥0.6→写下「不引入向量检索」并停止投入；None→无法判定保持现状）、`markdown_retrieval`、`_run_retrieval_suite`，`--suite` 扩为 `(legacy,behavior,v2,retrieval)`，retrieval 分支早返回（写 json+markdown、打印指标与结论、**返回 0 不门禁**）。**前提修正**：roadmap 说「用 12 条行为任务 + 30 条 fixture 的 trace 建基线」，但 trace 不含「问题→应命中文件」的标注真值，无法直接算 recall；改为人工标注 20 条定位真值（query→target file），在仓库自身上检索，这才是 hit-rate 的可证伪定义。书面结论落地 `docs/BENCHMARK_EVALUATION.md`「检索决策门（M4-T7）」节 | 实测 `--suite retrieval`：`recall@1=0.65 recall@5=0.90 MRR=0.75 cases=20` → 结论「不引入向量检索」（recall@5≥0.60）。`tests/test_retrieval_eval.py`（8 条）：真实数据集 schema/id 唯一/≥12/相对路径、6 类畸形数据集均 `ValueError`、合成工作区 recall@1==mrr==2/3 且故意 miss 的 case `first_relevant_rank is None`、多目标部分命中 recall≤0.5、决策三档阈值（==floor 通过/0.59 建议 embedding/None 无法判定）、**`test_real_dataset_clears_floor_backing_the_written_conclusion` 守护已提交结论**（recall@5 跌破门槛即红）、`main --suite retrieval` 写 json+md 含「结论」返回 0、坏数据集返回 2。回归全绿：`test_benchmark_runner`(15)、`test_behavior_bench`、`test_bench_tasks`(12)、`test_bench_compare`(22)、`test_core`、`test_pricing`(13) |
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
| M7-T3 Web 交互式权限审批 + 声明式 allow/deny | ✅ | Web 端把 `missing_task_write` / `missing_task_exec` 变成前端审批弹窗（允许后继续、拒绝落 `tool_denied_by_policy` 审计）；新增工作区 `.minicc/permissions.json` 规则层：`deny` 绝对且在询问前短路、任务开关与 allow 都越不过，`allow` 只跳过交互提示、绝不升级（plan 仍只读、联网仍需任务级授权），文件损坏时忽略规则并把解析错误进审计 | `tests/test_permissions_approval.py`；提交 `1da701a` |
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

| M8-T14 宿主关闭时 worker 句柄不得成为泄漏、且关闭语义要说得清（已按选项 A 实施） | ✅ | 干净关闭 = 写 cancel 标志 → 有界等待 5s → `terminate()` → 回收句柄 → 用租约围栏把记录落成 `cancelled`（并清掉 cancel 标志，避免复用它 id 的重试被瞬间取消）；崩溃 = 完全不碰 worker，留给 auto-resume 接管。`pytest -q -W error` 全量 **904 passed**（此前同一命令 6 failed / 7 errors）。契约测试改写成**真崩溃模拟**（宿主跑在子进程里被 `kill()`）。完整取舍、先红证据与那条「在测试里短路 `shutdown()` 不叫崩溃模拟」的教训见「第四批」第 1、5 行 |

| M8-T16 429 配额窗口不得把任务打成失败（M6-4 真跑暴露） | ✅ | 根因是可测量的一句话：**整个重试预算只有 15 秒，而限流窗口是 60 秒**。`openai_provider._wait_retry_after_or_exponential` 对 429 也走 `min(60, 2^(n-1))` → `max_retries=4` 时累计睡眠 1+2+4+8=15s，五次尝试全部落在同一个未完成的一分钟窗口内，`reraise=True` 把它原样抛给 `agent/loop.py:840` 的 `LLM 调用失败: …`，任务判死。用假网关（`httpx.MockTransport`，不消耗真实配额）量出边界：限流器 3s/15s 后解除时能恢复，**60s 后解除则 15.06s 就放弃**，错误串与 bench 现场逐字相同。修法按错误类别分开退避：速率限制类走 `_RATE_LIMIT_BACKOFF_BASE_SECONDS=15` 起底的指数（15/30/60/60，累计 165s，仍受 60s 单次上限与尝试次数上界约束），其它瞬时错误保持 1/2/4/8 不变，`Retry-After` 头仍然优先。修复后同一探测 60s 窗口 **105s 恢复成功**（4 次 HTTP 尝试） | 新增 `tests/test_rate_limit_retry.py`（6 条）：预算断言 `sum(waits) >= 60` 且逐项 `[15,30,60,60]`（**短路修复后此条报 `retry budget 15.0s is shorter than the limiter window`，即红→绿判据**）、非限流错误仍是 `[1,2,4,8]`（防过度修正）、`retry-after: 3` 覆盖底值、`_is_rate_limit` 认被包装成 `RuntimeError` 的 429 文本且不认 500、e2e 假网关 429→429→200 恢复且恰好 3 次尝试、持续 429 仍在 `max_retries+1` 次后报错（等得久 ≠ 无限等）。LLM 域回归 `test_rate_limit_retry`+`test_core_llm`+`test_responses_streaming` **26 passed** |

| M8-T17 评测里唯一的真实能力失败：`v2-license-mit` 不收敛（**结案：不是能力失败，是一条按构造不可满足的确定性门**） | ✅ | 判据（`review_rounds` + `objective_oracle`）接出来后一次真跑就定案：四轮评审的 `missing` **一字不差**，且 `objective_oracle.passed=true`——交付物本来就对。根因在 `agent/completion.py` 的写后检查门：`LICENSE` 没有后缀 → 被当作源码改动 → 要求跑 `tool_policy` 白名单里的真检查器，而该 fixture 没有任何可跑的东西（跑 `pytest` 非 0 退出同样不清门）。修法：`suffixless_prose`（license/copying/notice/authors/…）认回文档，走 `read_file`/`git_diff` 这条本来就客观的支路；**改代码要跑检查器的规则没有放松**（`Makefile` 由回归测试钉住）。真跑同一条命令：16 轮/127 487 tokens/134.5s/failed → **6 轮/33 078 tokens/31.2s/completed 且 passed** | `tests/test_check_selection.py` 2 → 4 条：`test_a_suffixless_prose_write_demands_a_demand_that_can_be_met`（**先红**：桩回 HEAD 版本即报 `为最近的代码修改运行相关测试…`）、`test_extensionless_build_file_still_demands_a_real_checker`（防放松）。证据：`output/m8_t17_repro.results.json`、`output/m8_t17_oracle.results.json`、`output/m8_t17_after_fix.results.json`；分析见「第七批」 |
| M8-T18 配置面：`getattr` 兜底读出一个 `Config` 上根本不存在的键（「旋钮」永远拧不动） | ✅ | M8-T17 结案时顺手发现 `max_completion_continues` 是 `getattr(self.config, ..., 3)` 而 `Config` 无此字段。**这条不是孤例，是一类**，所以先把它变成可执行门再修：`tests/test_config_surface.py` 用 AST 扫 `minicc/**/*.py` 里所有「target 末段是 `config` 的三参数 `getattr(obj, "字面量", 默认)`」，要求字面量必须是 `dataclass fields(Config)` 之一，并带 `_MIN_SITES = 30` 下限防空清单假绿。**门第一次运行就报出三个死旋钮**：`max_completion_continues`（web.py:1434）、`anthropic_base_url`（main.py:618 + web.py:1390，两处都是 `or self.config.base_url`，所以 Anthropic 网关挂在自己域名下这件事一直配不了）、`task_worker_runtime`（task_manager.py:1011，全仓库仅此一处引用、没有任何实现语义 → 条件恒真）。修法分别对应三种判断：前两个**声明成真字段并接上 env + 项目层键**（`MINICC_MAX_COMPLETION_CONTINUES` 夹在 1..8、`MINICC_ANTHROPIC_BASE_URL` 空串仍回退 `base_url`，行为不变）；第三个**删掉幽灵条件**而不是新造一个旋钮（删除后的行为与今天逐字节相同，比"补一个没人实现的开关"诚实）。 | `tests/test_config_surface.py` 2 条（门 + 下限），`tests/test_project_config.py` 16 → 20：默认/项目层/环境变量三层可达、`0/-4/99` 夹到 `1/1/8`、非整数抛 `ConfigError`、`anthropic_base_url` 去掉尾斜杠。**门的红→绿是拿 HEAD 版 `config.py` 量的**：桩回去即报 `anthropic_base_url at minicc/main.py:618；... at minicc/web.py:1390；max_completion_continues at minicc/web.py:1434` |
| M8-T19 封顶仍是「同一句要求重复四轮才停」（**观测已落地，停止策略未动**） | 🟡 前进一格 | M8-T17 结案后这条失去了触发样本，记录以免被当成已修。「两轮相同就停」会误杀「agent 第一轮没听懂、第二轮才去做」的正常收敛；要做须带活动信号（评审要求与上一轮相同 **且** 本轮没有新增检查类工具调用）。另有一条口径：bench 的 `code_revision` 记 HEAD，工作区未提交的改动不会改变它，可区分代码版本的只有 `runtime_source_sha256`。**2026-09-23 更新**：这条缺的「可满足性见证」现在有了——`completion_verdict_repeated` 事件在真实任务里会把「逐字复读 + 本轮零新增活动」连同 `tool_events` / `verification_runs` / `last_verification_status` 一起落到任务快照，停止时机仍归 `max_completion_continues`。见下方 M8-T26 |
| M8-T26 评委复读的成本从「隐含」变成「每条任务可查」：新增观测事件，不动收敛判据 | ✅ | 见下方「第十三批 M8-T26」。M8-T19 挂起的真正原因是**缺可满足性见证**而不是缺样本：上一批已把成本钉成 `calls["agent"] == 4`（评委复读一次 = 多烧一整轮 agent），但一条任务真跑完，记录里只有「未收敛」四个字，看不出**是哪一轮开始评委在说同一句话**、也看不出那一轮 agent 到底做没做事。改法是把判据的两半**先做成可观测**：`missing + next_action` 逐字相同 **且** `(tool 事件数, 验证次数)` 与上一轮完全相同 → 发 `completion_verdict_repeated`（`status: "ok"` 沿用同类观测事件 `dependency_aware_repair_scope` 的先例，不发明新状态值），`detail.action = "observe_only"` 把「这不是停止规则」写在数据里 | 两条门各守一半，**两半都是承重的**（逐字红→绿）：条件短路成 `False` → 观测事件数为 0，`assert (4 == 4 and 0 == 3)` 红；只留 `repeats` 去掉活动比较 → 「每轮真的去读一个新文件」那条反误杀门红（事件在不该出现的地方出现了）。反误杀那条断言形如「不存在某事件」，因此它自己必须带承重证据：同一测试里 `seen["judge"] == 4`（评委确实复读了）与 `len(read_paths) >= 3`（活动确实增长了）都在，缺席断言才不是空转。**顺带量到的产品事实**（写反误杀门时撞出来的，不在计划里）：只读任务里 agent 反复调用工具**并不能**走到「评委复读」那一步——loop 自己的恢复保护会先接管，事件序列 `stagnation_replan → recovery_guard → task_stagnation_recovery` 连跑两轮后以 `Agent 在错误路径恢复阶段没有取得新的工作区证据` 结束，**完成评估根本没被调用过**（`judge == 0`）。所以「评委连续复读」只发生在 agent **每轮直接给文字结论**的形状里，M8-T19 那句「要做须带活动信号」的假设需要修正：有活动信号的只读路径已经被另一套保护管住了。**边界**：事件不发=没有停止变化（`calls["agent"] == 4` 那条老断言仍是绿的）；本批不真跑模型，因为它不触碰任何线格式、计价或用量形状（上一条真机腿已由 M8-T24 量过），且真实评委几乎不会逐字复读——用 quota 去等一个小概率字符串相等，不产出判据。全量 **997 passed** | **口径纠正（本批实测）**：这条当时写的「还没有样本」**不成立**——`tests/test_core_agent.py::test_completion_continue_loop_is_capped_instead_of_burning_turn_budget` 早就是一个**确定性失速样本**：假 provider 让评审连返 4 次**逐字相同**的判定（同一 `missing`/`rationale`/`next_action`），实测 `calls["agent"] == 4`，也就是**评委复读一次，就多烧一整轮 agent**（默认上限 3 次 continue → 4 轮）。已把这条断言补进该测试，把成本从隐含变成钉住。仍然不动收敛判据，因为缺的不是样本而是**可满足性见证**：样本里的要求（「再做一轮检查」）本身没有客观判据说它已被满足，在它上面改「两轮相同就停」依旧是凭 1 个 fixture 调收敛策略。下一步该用的是 M8-T17 那种「客观 grader 已通过、评委仍在复读」的组合 |
| M8-T27 `/api/metrics` 的五个分项必须与它们所装饰的总数同源（新增围栏，**不是**修复） | ✅ | 见下方「第十四批 M8-T27」。`usage` / `cost_usd` / `by_model` / `tasks_by_status` / `subtask_rows` 是同一批行算出来的五个数，读者会把它们**并排读**（「这笔总额是哪个模型花的？」）。M8-T23 立的是「总额 == 单任务快照之和」，**分项 vs 总额**这一层当时没人管。先离线量了一遍：今天是自洽的（`by_model` 逐 key 求和 == `usage` 的 2080/325/2405、非 None 成本之和 == 总额 0.00062、`sum(by_status) == task_count == 3`、`task_count + subtask_rows == 索引行数 5`）。**所以这一批交付的是围栏不是修复，这句话必须写在文档里**，否则后人会把「新加了一条门」误读成「这里曾经有 bug」 | 一条门（`tests/test_logging.py::test_metrics_breakdowns_add_up_to_the_totals_they_are_shown_next_to`）：先断言形状非平凡（3 个根任务 / 2 个模型 / `priced=1, unpriced=2` / `total_tokens > 0`），再断六条同源关系；顺带把空范围那一格补齐（`by_model == {}` 且 `tasks_by_status == {}`——只断 `task_count == 0` 会让「0 个任务却有 3 个模型」这种坏聚合器过关，是哨兵规矩的另一面）。**承重量**：两处机械变异，各只红这一条门——分项不再累加 token（总额仍然正确）→ `prompt_tokens does not add up across by_model / assert 0 == 2080`；状态分项每行多计一次 → `assert 6 == 3`。全量 **998 passed** |
| M8-T28 触顶报错把「评委的判断」当成唯一结论，三种不同的结束印成同一句话 | ✅ | 见下方「第十五批 M8-T28」。探针（写入 `out.txt` + 评委逐字复读）量到的真实事件轨是 `write_file → verification_required_before_finish/error → verification_guard/error → verifier/verification_skipped → completion_judge/completion_continue ×4 → completion_continue_capped`：**客观验证确实跑了，状态是 `skipped`（工作区里没有可运行的检查）**，而报错只说「完成评估连续 4 轮要求继续但未收敛…请根据缺失项检查后重新提交任务」——把用户支给评委的意见，真正可操作的事实却是「这里没有可执行的验收条件」。三种结束（验证通过但评委不同意 / 验证被跳过 / 只读任务根本没触发验证）此前共用一句话，只有中间那种能靠补验收命令解决 | 抽 `_unconverged_verification_note(verification_results)` 按最近一次客观验证状态分支，并把 `verification_runs` 与 `last_verification_status` 加进 `completion_continue_capped` 的 `detail`（记录要能自己说明分歧在哪一侧，不靠人回读事件轨）。两条门：只读那一格断 `verification_runs == 0 / last is None` 且文案含「没有运行客观验证」；写入那一格断 `verification_runs == calls["judge"] == 4`（**每轮复审都重跑一次验证**，这条是量出来的，写死 1 会被自己的门判红）+ `last == "skipped"` + 文案含「验证被跳过」并**显式断它不等于只读那句**。**承重量**：把注解退回旧的固定文案 → 两条门同时红（`assert '没有运行客观验证' in '…请根据缺失项检查后重新提交任务'` / `assert '验证被跳过' in '…'`）。停止时机与状态判定一格未动（仍是 `未收敛` + `calls["agent"]` 原值）。全量 **999 passed** |
| M8-T29 检索层写着「凭据文件永不进索引」，而守这条的常量从没被引用过——命中本身就是「叫 agent 去读它」的指针 | ✅ | 见下方「第十六批 M8-T29」。自证句清扫扫到 `retrieval.py` 文档字符串第 6-7 行「secret files such as `.env` are never indexed」。量法：造一个同时放着 `.env`、`secrets.json`、`credentials.toml`、`service-account.json`、`deploy.pem` 与正常源码的工作区，直接问索引「api key token secret」。**结果分两半**：① 哨兵**值**确实没有出现在任何命中里（`EvidenceHit` 只带 path/reason/symbols/test_failures，不抄正文）——所以这不是内容泄漏；② 但 `secrets.json` 以 12.0 分**排在这次查询的第一名**，`reason` 写着 `filename+path+content+fresh`。索引回答的是指针，而指针的意思就是「去读这个文件」，对凭据库来说和把它抄进上下文没有区别。同时 `SECRET_FILENAMES = {".env", ".env.local"}` 在全仓库**只有一处定义、零处引用**：`.env` 今天不进索引，是因为遍历里那条 `name.startswith(".")` 与扩展名白名单**恰好**挡住了它，不是因为有人写了这道门 | 把常量接成真规则：`is_secret_filename(name)` = 显式名单 + `.env*` 前缀 + 密钥后缀（`.pem/.key/.p12/.pfx/.kdbx`）+ **数据文件**里的 `secret(s)/credential(s)` 词干与 `service-account` / `-api-key` 名称；遍历处一次 `continue`。**关键取舍是后缀分流**：`credentials` 这个名字在 `.toml` 上是凭据库、在 `.rs` 上是普通源码——第一版没有后缀区分，被自己写的边界门判红（`assert ['credentials.rs'] == []`），于是引入 `_SECRET_STORE_SUFFIXES`，代码扩展名一律不排除。README 与文档字符串同步改写，把「命中=指针」这件事写成规则存在的理由 | 两条门，一正一反。正向（`test_credential_stores_are_never_offered_as_evidence`）：断 `indexed == 五个正常文件`（**精确集合相等**，多进一个凭据库或误杀一个源码文件都红）、断凭据名不出现在 `search("api key token secret credentials")` 的路径集合里、断哨兵值不在序列化命中里、并断 `files_indexed == 5` 防空索引假绿。**承重量的不是「不出现」而是「两边都算」**：把判定短路成 `return False` → 红在 `Extra items in the left set: 'secrets.json' / 'nested/secrets.yaml' / 'service-account.json' / 'credentials.toml'`。反向（`test_the_secret_name_rule_is_exact_not_a_substring`）：11 个必须拦 + 10 个必须放行**逐名列成数据**（含 `credentials.rs`、`secrets.go`、`secrets_store.py`、`secret_rotation.py`、`keys.md`），这条门就是抓到过度排除的那次修正。**边界**：只挡**索引面**——`read_file` 等工具按权限仍能读到凭据（那是权限面，另一条门守着）；`config.json` 里放真密钥不算「凭据文件名」；名字规则挡不住改名后的凭据库（`db.json` 里塞 key），那种要靠内容脱敏，本批不假装覆盖。全量 **1001 passed** |
| M8-T30 关掉自己上一批写下的边界：worker 重连回来的父任务既不能少记子树、也不能二次相加 | ✅ | 见下方「第十五批续 M8-T30」。M8-T24 把 `_reconnect_worker` 记成「这条支路不汇总」。动手前先读镜像怎么造结果，读到的是 `"tokens_used": dict(snapshot.get("usage") or snapshot.get("tokens_used") or {})`——**一个已汇总的父任务，它的快照本来就含子树**，所以「那里也调一次汇总」会把 525 变成 925：**修法比缺口更危险**（缺口是少记，误修是多记，而数字变大不会报错）。改成让**负载自己声明**：汇总时把 `children_rolled_up: true` 与同步后的 `tokens_used` 一起写进 `result`，`apply_result` 认这个声明（认了保持置位，没认才清零），`_reconnect_worker` 于是可以安全调用汇总
| M8-T31 刚给自己加的「负载自己声明汇总」是个可被模型滥用的通道——声明改由主机字段承载 | ✅ | 见下方「第十五批续二 M8-T31」。M8-T30 让汇总把 `children_rolled_up` 写进 `result` 负载，重连时再读回来。**下一批回头看就发现落点错了**：`result` 的内容来自模型/worker 的产出，于是任何被计费的一方都能在负载里夹一个 `children_rolled_up: true`，让 `apply_result` 保持清零后的状态、把子树花费**从账单里抹掉**。这和 M8-T24 立的原则是同一句——「结果负载不许覆盖主机维护的字段」——我只是把新字段写到了错的那一侧。**这批没有新缺陷报告对象，缺陷是我自己三批前引入的**，来源相同：`snapshot()` 末尾 `output.update(result_payload)` 会再用负载覆盖记录字段，所以负载里那个键既进得来也出得去 | 三处一起改，缺一不可：① `snapshot()` 的主机字段保护块补上 `children_rolled_up`（负载再也翻不动它）；② `TaskResult.from_payload` 把这个键从 metadata 透传里**剔除**（负载带不进来）；③ `WorkerSnapshotMirror.result()` **只在快照主机字段为真时**才把声明补进负载——「只为真值加键」是刻意的：无条件加 `False` 会让两种执行器的负载不同形，正是 M8-T30 那条 durability 契约门判红过的地方。汇总侧不再往 `result` 里写声明 | 门的 (c) 段整段换了方向，而且**是新行为先让它红**：原来那句 `assert to_payload().get("children_rolled_up") is True`（透传）改成了 `assert "children_rolled_up" not in to_payload()`（剔除）。新增第三种负载：**只有 result 体里声称、快照字段却没说**的伪装负载（`spoofed`）——它必须什么都换不来，仍然按未汇总处理。三段关系也一并钉住：主机声明为真 → 不再相加；无声明 → 补进子树（525）；有声明却丢声明（假设性回归）→ (a) 段红。全量 **1002 passed**（条数不变， strengthened 的是既有那条门的强度）|
| M8-T32 「`/api/*` 有多少被覆盖」这个数，本环境算得出来——但要靠把每条路由真打一次，不是靠匹配字符串 | ✅ | 见下方「第十七批 M8-T32」。M4-3 的百分比因为 `coverage`/`pytest-cov` 都没装而长期标成「算不出来」。这批先试了两种**能算出来**的静态量法，两种都以相反的方向撒谎：① 把路由名与测试里的字符串常量做双向 `in` 匹配 → **100%**（任何共享前缀的一对都能满足，空串更是全都满足）；② 收紧成「测试里存在以该路由为字面量的请求调用」→ **GET 17.6% / POST 16.7%**（六个测试模块用 f-string 拼路径，静态匹配看不见）。两个数都不能拿来当验收。**真正可执行的量法只有一个**：从分派器 AST 取路由表，然后**逐条真发一次请求**打起来的服务 | 新门 `tests/test_http_route_inventory.py`（4 条）：AST 枚举 `do_GET`/`do_POST` 里与 `path` 比较的 `/api/` 字面量，带**下限 + 具名路由必须在册**（`/api/chat`、`/api/tasks`、`/api/tasks/batch`、`/api/metrics`）防空清单；GET 逐条原样请求，POST 逐条发 `{}`（空对象是「绝不该把处理器打崩」的最小输入），统一断 `status < 500` 且非 2xx 响应体带**形状合格**的 code（snake_case 或 JSON-RPC 数字）。实测：**GET 17/17、POST 12/12**，打印 `MINICC_ROUTE_COVERAGE {...}` 把数字留在测试输出里。**门的两次自我纠正都记进代码注释**：先误判 `/api/worktrees` 的 `worktree_error` 不合规——是我手抄的 code 白名单漏了它；改成「从源码收割词表」后又红了一片，因为 `"code": "..."` 这个语法模式在产品里同时是**事件码**的写法，收割到的是错宇宙的名录（`batch_finished`、`approval_requested`…）。**从错模式派生的清单，和手抄一样不可信**，最终只留「code 必须像个稳定标识符」这一条形状判据。**红→绿承重量**：把形状判据换成不可能匹配的 `^ZZZ-impossible` → 3 条同时红，证明 GET/POST 两侧真的有拒绝响应在被检查（不是所有路由都 200 交差）。**边界（这条不覆盖什么）**：① 只枚举 `path == "..."` 的**精确**路由，`/api/tasks/<id>`、`/api/tasks/<id>/events` 这类 `startswith` 分派不在册——它们的正路有各自模块的测试，但没有这张总表；② 「答了/拒了」**不等于**每条路由的成功路径被覆盖，那是别的模块的事，这条门保证的是**整个分派链没有哑火或裸 500**；③ 不是行覆盖率，本环境仍然算不出那个数，也不拿这个数冒充。全量 **1006 passed** |
| M8-T33 M8-T32 那个 100% 的洞要有名字：`startswith` 分派的路由族以数据登记，新族出现就把门判红 | ✅ | M8-T32 的边界自己写着「`/api/tasks/<id>` 这类前缀分派不在总表里」——一句话的边界，下一个人照样会把 100% 读成全量覆盖。这条把那句边界变成**机器可查的登记表**：AST 扫 `do_GET`/`do_POST` 里所有 `path.startswith("/api/...")`（剥掉 `/api/` 那个 404 兜底守卫），断言集合恰等于 `_UNPROBED_FAMILIES = {"/api/tasks/"}`。**为什么不在这里真去打这些路由**：其中 `/api/tasks/<id>/events` 是流式端点，通用探测器会挂在 socket 上直到超时——它需要的是**会读流的探针**，不是把 URL 塞进现有循环；这个理由随登记表一起写在代码里，而不是留在文档里 | 一条门（`tests/test_http_route_inventory.py::test_prefix_dispatched_families_are_probed_or_parked_with_a_reason`）。**承重量**：把登记表清空 → 红在 `either probe it or record why not: ["/api/tasks/"]`；另有 `assert "/api/tasks/" in families` 单独守住「枚举器确实找到了真东西」，于是「空集合等于空集合」这种假绿结构上不成立。全量 **1007 passed** |
| M8-T34 给前缀分派与流式路由补「会读流的探针」，把 `_UNPROBED_FAMILIES` 逐条清空 | ✅ | 原文这里指向「第十八批 M8-T34」，而那一节是 M8 退出标准记录、并没有这一小节——**指向不存在段落的引用**，M8-T35 复核时发现并改指真实证据：提交 `cdd891e`（登记族）与 `b60e225`（流式探针），本行本身即结论全文。`_UNPROBED_FAMILIES` 已改名为 `_PROBED_FAMILIES = {"/api/tasks/"}` + `_PARKED_FAMILIES: dict[str, str] = {}`（parked 必须带非空 reason，空串也算没登记）。新增 `_DYNAMIC_ROUTES` 把 4 条动态路由（GET `/{id}`、GET `/{id}/events`、POST `/{id}/resume`、POST `/{id}/cancel`）并入 `_route_table`，于是 GET/POST 下限与「具名路由在册」断言仍然咬得住；通用逐条探针显式跳过含 `{task_id}` 的模板。harness 扩了三处：`submit()` 用 `_defer_schedule` 提交一个**真任务**拿 id（不启动 worker，探针不与真跑竞争）、`read_sse_prefix()` 用 `read1` 读到至少一帧即挂断（带 deadline 与字节预算，绝不等到流自己结束）、`_target()` 按 URL 各部分拼装（`quote(整串)` 会把 `?` 编码成 `%3F`，把查询串喂进 task id —— 这是探针自己先踩到的 bug）。新增 5 条门：动态路由 answered、未知 id 断 `task_not_found`（详情 + SSE 两条）、SSE 拿到帧且 `elapsed < 10`、`?after=0` 重放也拿到帧。**承重量**：把 `_PROBED_FAMILIES` 清空 → 门红并点名 `/api/tasks/`；给 parked 一个空 reason → 红（临时门跑过后删除，未留在仓库）。`tests/test_http_route_inventory.py` **9 passed**，与该文件同时跑的 `test_http_surface.py` 合计 **86 passed**（`-W error`） |
| M8-T35 把 M4-3 那句「口径可复现」拿去复现：量法原来在仓库外，而且它量的那个东西一次请求就能喂满 | ✅ | 见下方「第十九批 M8-T35」。两个独立缺陷：① 产生 ②（分派点覆盖）的脚本只在 `Temp/` 里，硬编码绝对路径，仓库内的两条命令算不出它；② ② 的定义是「这条路由的比较行跑过没有」，而平铺 `if/return` 链上**任何一条走到链尾的请求**都会把整链的比较行点亮——实测 `POST /api/nope` 一条请求 = POST 侧 A 14/14（100%）、B 0/14。修法：量法进仓库（`scripts/route_coverage.py`，A/B 两个数分开报、只对 B 判红、带分母下限、`--check` 非零退出），并给它配「守量具的门」`tests/test_route_coverage_measurement.py` 7 条（三种分派形状都要看得见 / A 能在全覆盖的表象下藏住零分派 / B 只被分支体行点亮 / 一行不能同时满足两个兄弟路由 / 文本阅读器与 AST 阅读器不许分歧 / 分母塌了要报问题而不是报百分比 / 文档那条命令端到端真跑一遍）。**过程里当场撞出第二次的同一类错**：第一版只读 `If.test` 整体，`startswith(...) and endswith(...)` 是 `BoolOp` 因此三条真分派点静默消失、分母 34→31 而**两个数照样都是 100%**——靠「笨文本阅读器 vs AST 阅读器」对账才抓到 | **红→绿逐字**：把 B 退化回 A（`entered` 用 `compare_line`）→ `assert 0 == 1` 与 `assert 4 == 0` 两条红；把 `_test_predicates` 的 `ast.walk(test)` 换成只看整体 → **6 条红**，其中 `--check` 那条报 `INVENTORY PROBLEM: webserver.py:355/566/570 compares \`path\` against '/api/tasks/' in plain text but no dispatch site claims it`，而同一份输出里 31/31、12/12 仍是 100%（这正是必须靠退出码而不是靠读数字的原因）。**换口径后结论未变**：B 也是 GET 20/20、POST 14/14。顺带修掉 `tests/test_http_surface.py` 里那句已经过期的「No coverage tool is installed here and CI does not run one, so that percentage cannot be computed」（`coverage 7.16.1` 已在 dev extra）。全量 **1018 passed**（`-W error`，266.32s，exit 0） |
| M8-T36 文档里那句「见下方第N批」也是一条断言：给它一个会红的门，顺便给上一批手抄的路由清单补第二个阅读器 | ✅ | 见下方「第二十批 M8-T36」。触发点不太好看：M8-T35 记录 M8-T34 那个悬空引用时，把 `见下方「第十八批 M8-T34」` **原样重发进了新写的句子里**——描述错误的句子自己带着同一个错误，而人读不出自己刚写的话。工具进仓库：`scripts/doc_pointers.py`（实测 19 份文档、33 条可查指针、21 条相对链接，`--check` exit 0）。两条规则：定位符必须落在**存在的标题**上；同一指针点名的编号必须在那一节的**标题或表格行标签**里被声明过——「在正文里出现过」是自我满足判据（指针自己就拼着那个编号），与上一批「比较行跑过≠覆盖」同构。中文里 `见` 不能当标记（可见、意见、见证、预见），所以只抽「名字里带定位符或编号」的片段，其余 **84 条**（写出这段记录时的实测值）计为 `unresolved` 并打印，不做静默丢弃。**这个数每写一段证据就会涨**：本批这段记录自己就新增了两条不指名定位符的指针（如「见上表末格」），所以下文不再引用它当结论，要当前值就跑一次命令。量出 4 条真悬空引用并逐条改掉：roadmap `:939`、`:1091` 写的「第四节 M4-3 / M1-1」指向了一个**确实存在但不是那一处**的标题（「四、明确不做什么」）；`:754` 的「第十八批 M8-T34」；README `:289` 的「审核文档第十二节」没把文件名写进指针。`tests/test_doc_pointers.py` 13 条门（含「引用写在代码区间里是示例不是断言」这条新规则自己的门）。同时给上一批我手抄进测试的 `_DYNAMIC_ROUTES` 补**双向**对账：`tests/test_route_coverage_measurement.py` 7 → 11 条——前缀族没有对应模板=漏报、模板后面没有分支=幻影探针、豁免必须带非空 reason 且**豁免本身失效也要报**（`_CATCH_ALL` 现在只有 `GET /api/*` 一条 404 兜底） | **红→绿逐字**（把原文在内存里还原后复测；仓库内的复现路径是 `_BAD_DOC` 那条门，见第二十批）：`[POINTER] ROADMAP_TO_PRODUCT.md:754 「第十八批 M8-T34」 说 M8-T34 在「M8 退出标准真跑记录（第十八批，2026-09-23）」里，那里没有这个编号`——注意这一条不是「标题不存在」，标题存在、编号没登记，这正是「声明」比「出现」强的地方。**门是活的（靠变异而不是靠断言）**：把 `_mask_code` 去掉（工具不再忽略代码引用）→ **3 failed, 10 passed**，红的是 shipped-docs 门、端到端门和新加的引用门；两个阅读器的对账各造一次假（模板后缀打错 → 同时报漏报与幻影；多塞一条不存在的模板 → 报幻影）都是 **1 failed**；两次变异后脚本都按字节还原（`restored byte-exact: True`）。**这批我自己犯的同类错有三处**，全部留在注释或门里：① 抽取 `_DYNAMIC_ROUTES` 只认 `ast.Assign`，而它写着 `dict[str, list[str]]` 注解，于是报「清单没了」；② 编号检查最初是 `identifier in text`，指针自己就满足它；③ 新写的「代码引用」门断言 `unresolved == 1`，实际是 0（掩码把整段连标记一起抹掉），随后又用 `sum("第十八批" in p.detail)` 去区分两条 complaint——每条 detail 都整段引用了 span，数它什么也区分不出来。**错的三次都是我的期望，不是工具**；按 M8-T35 的口径：不能拿计数代理做归因。**边界（不声称的东西）**：不指名定位符的指针完全查不到，84 条 `unresolved` 就是没被守住的面积；「声明在标题/行标签」证明编号登记过、不证明那句话语义正确；写在代码区间里的真悬空引用同样看不见（这条规则的门已把代价写进 docstring）；跨文档指针必须把文件名写进指针本身，否则只在本文档内解析；`doc_pointers.py --check` 与 `route_coverage.py --check` 都**只由测试和本地调用**，没接进 CI | 本批新增 13 + 4 = 17 条门；全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1035 passed**（245.16s，exit 0；上一基线 1018，差额恰好等于新增门数 17，没有门被悄悄改掉或跳过） |
| M8-T37 行内代码里的 `tests/test_core.py:1510` 也是一条断言：给「文件 / 行号 / 测试名 / 属性」补一个会红的阅读器，并让每条豁免自己付账 | ✅ | 见下方「第二十一批 M8-T37」。上一批的量具只读 `见/参见` 与 markdown 链接，**行内代码里的定位符一条都没读**（HEAD 的脚本里 `grep -c _EVIDENCE_TABLES` = 0）。补上的判据：代码片段里的路径、`路径:行号`、`路径.ext.属性`、`测试文件.py::测试函数名`、裸 `test_*` 都是可解析断言——文件要存在、行号不能越界、`::` 后的测试要真定义在那个文件、属性名要真出现在被引文件里；外加一个不带斜杠也能命中仓库文件的**第二阅读器**（正文里裸写的仓库路径也算断言）。把豁免清空后在 HEAD 文档上复测：**28 条红 / 21 条不重复断言**，逐条分派为 8 条文档写错（改文档）+ 13 条语义已变（9 个豁免键、六类理由），**静默吞掉 0 条**。豁免不是免检而是改性质：每条必须带非空理由、必须仍被某文档引用，否则自己就是红。量具自己的两处缺陷都在本批内被抓：**清单双计**（同一 span 计 2 次，打印 1524 而真值 794（都是当时的清单，本批定稿时已涨到 811）——被抓是因为新写的 `_evidence` 助手第一条断言就是它自己的计数）与 **五条解析根里四条是死行**（调用点实测 `<root> 544 / tests 2 / minicc 0 / scripts 0 / docs 0 / 兄弟目录 0`，而那张表看起来像策略）。**顺手当场纠正上一批的一句断言**：「`--check` exit 0」只在作者机器成立——干净 worktree 检出 HEAD 跑同一条命令是 **exit=1**，两条指向 output/playwright 下两张 png 的链接落在 `.gitignore` 声明的生成目录里（本机存在、不进仓库）；已列为下一批第一项 M8-T38，本批不扩范围去修别人的阅读器。**M8-T38 末尾又量出同源的第二件**：同一份 HEAD 的证据清单在干净检出是 782 条、在开发机是 811 条——形状判据读了工作目录，把「我这台机器上有什么」当成了「仓库里有什么」 | **红→绿逐字**（六条变异，每次跑完按 sha256 `71b05709db84` 字节还原并复验）：① 豁免永不生效 → `--check` exit=1、`4 failed, 18 passed`，红在 floors / shipped-docs / 端到端 / 正文第二阅读器，逐字见第二十一批的转写块；② 把「先计数再豁免」换成「先豁免再计数」 → README 证据数 18→**8**，`INVENTORY` 那条下限红立刻点火，`3 failed, 19 passed`；③ 关掉「豁免必须带理由」检查 → `1 failed, 21 passed`，红在那条「豁免自己付账」的门；④ 往豁免表塞一个无人引用的探针键 → `2 failed, 20 passed`，红在端到端门与「豁免自己付账」门，报的是「已无任何文档引用，是陈旧登记」；⑤ 删掉 `web/src` 解析根 → `--check` 仍然 exit=0 而门红 `assert 2 == 3`（活性门：每个根都必须至少答上一条在仓文档里真出现过的引用）；⑥ 让正文阅读器不再要求带斜杠 → `1 failed`，红在「`loop.py` 不算断言」那条。**还有一条假绿变异**：第一版 ③ 我写成「在字典字面量里把理由置空」，`--check` 与 22 条门全绿——因为同键在后一行覆盖了它，**变异根本没落地**。此后每个变异都断言锚点恰好命中 1 次并先 `compile()`，落不了的变异等于没测 | 本批新增 9 条门（`tests/test_doc_pointers.py` 13 → 22）；全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1044 passed**（217.20s，exit 0；上一基线 1035，差额 = 新增门数 9） |

| M8-T38 量具的清单必须是 HEAD 的函数，不是我这台磁盘的函数（上一批留下的两件，实测同源） | ✅ | 见下方「第二十二批 M8-T38」。上一批末尾量到的两件事——干净检出 `--check` exit=1、同一 HEAD 的证据清单在开发机 811 条而干净检出 782 条——根因是同一个：**凡从文件系统推出来的集合，都必须从 git 索引推出来**。落地口径三条：① 可接受的目录头从 `git ls-files` 的路径前缀推出（实测 HEAD 的 `iterdir` 版给出 19 个头，其中 **11 个只在这台机器上存在**：`.git`、`.minicc`、`.playwright-cli`、`.pytest_cache`、`.ruff_cache`、`.venv`、`build`、`dist`、`minicc.egg-info`、`node_modules`、`output`；索引版只有 8 个），落在磁盘专有头下的引用有 **64 条**（`.minicc` 33 / `output` 28 / `.venv` 3）；② 链接判据从二态换成**三态**——被跟踪→绿，被 gitignore→记为 `generated`（照计数、照打印、不报红），**本机有但 git 没跟踪→红**（这条只有作者看得见，所以必须留在红里）；③ 不在工作树里没有索引，退回存在性判断（保住临时目录里的合成夹具）。两条 png 链接没有走"写一条豁免理由"，而是由 `git check-ignore` 现场回答"这是生成产物"——**分类不是赦免**：判据来自仓库自己的忽略规则，规则改了判据跟着改。**顺手白捡一条**：新的活性门抓出上一批自己发的 **5 条死豁免键**（`AGENTS.md`、`CLAUDE.md`、`MINICC.md`、`review.md`、`keys.md`——不带斜杠的裸文件名永远不构成定位符断言，所以这五个键根本没有被咨询的机会），删掉后实测六类 14 个键全部命中 ≥1、合计答上 75 条引用。这里学到的判据是：豁免键有**两种角色**，挡红的（删掉 `minicc/web_static` → 恰好 2 条红）与准入的（删掉 `.minicc/` → 不报红、只是清单缩水），只按"删掉会不会红"量活性会漏掉后一种 | **红→绿逐字**（四格实测在**同一份干净 worktree** 里跑完，见第二十二批的转写块）：A 旧脚本 + 干净树 → exit=1，2 条 `链接目标 …png 不存在`，清单 **782/16**；B 新脚本 + 干净树 → **exit=0**，同一行尾部多出 `(2 of them into git-ignored generated output)` 与 `over 228 tracked files`；C 旧脚本 + 种入四个生成目录 → exit=1 但**红集合换了一批**（32 条，其中 30 条 `output/…` 证据、1 条 `.venv/Scripts/python.exe`），而清单变成 **811/17**——与开发机一字不差，这就是"811 从来不是文档的内容、是磁盘的内容"的机械证明；D 新脚本 + 同样种目录 → exit=0、仍是 782/16。**四条变异**（基线 sha256 `405dc6168fb3`，每次跑完字节还原并复验）：A `_top_level()` 改回 iterdir → `7 failed, 19 passed`；B `_holds()` 退回 `.exists()` → `1 failed, 25 passed`（红在"只有本机有的文件在本机也算红"那条门）；C `check-ignore` 恒答否 → `4 failed, 22 passed`；D 活性门循环不跑 → `1 failed, 25 passed`，逐字 `assert [] == ['豁免 zzz_noth…则现在挡不到东西，是死行']`。**变异 A 的锚点是 CRLF 撞的**：`scripts/doc_pointers.py` 全文 929 行都是 `\r\n`，多行锚点用 `\n` 写就命中 0 次——驱动强制 `count == 1` 才落盘，这条断言第一次是**用来拒绝一次根本不落地的变异**的 | 本批新增 4 条门（`tests/test_doc_pointers.py` 22 → 26）；全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1048 passed**（234.05s，exit 0；记录定稿后同命令复跑仍 1048 passed / 523.91s；上一基线 1044，差额 = 新增门数 4）。定稿实测 `795 条证据断言 / 16 条正文断言 / 228 个被跟踪文件`，与上一批在干净检出量到的 782 同一口径（多出的 13 条是这段记录自己写的） |
| M8-T39 那 102 条「没指名定位符」的标记不是一件事，是六件事——而其中一件根本不是指针却**通过了检查** | ✅ | 见下方「第二十三批 M8-T39」。上一批的总结行写着 `41 pointers (102 spans name no locator)`，那个括号读了二十年也不会告诉任何人下一步该做什么。把 102 条逐条摊开：其中 **69 条是「见」作为词素或动词接在普通散文后面**（可见流式答案、未见修复记录、零用户可见收益…），**9 条的落点是一个 markdown 链接**（链接阅读器已经在查它的目标），**7 条的落点是一个代码片段**（证据阅读器在查），**3 条指向一个散文里的路径**，剩下 **15 条是货真价实的指针但没有可解析定位符**（`口径见下方注记`、`全量数字见上表末格`、`见本批末尾`）。**最值钱的一条不在这个括号里**：`可见价值低于 M6–M8 任何一项` 被抽成了指针、并且**绿着通过**——M6、M8 两个编号确实都在这个文件里。一条假指针比一个未覆盖的缺口更糟：它往"已核验"那一栏里记了一笔 | **红→绿逐字**（四条变异，基线 sha256 `41efad1eaf6f`，每次跑完字节还原并复验，还原后 `32 passed`）：① 取消「必须是引用」判据 → `3 failed`，红在词内标记门、夹具分箱门与分箱下限门；② `_ID` 退回 `\b` → `2 failed`，红在"每种引用形状都被抽到"与"中文旁边粘着的编号仍是编号"；③ 把 `boxes[box] += 1` 移到"是指针才计"之后（一箱停止计数） → **`13 failed`**，包括那条新写的 `RECONCILE` 门；④ 总账里少印一箱 → `1 failed`，红在"打印出来的账要加得起来"。**这条判据是被两条旧门教出来的**：第一版只认「引用词开头」，`test_appendix_pointers_resolve_by_letter` 当场红——`附录` 不在引用词表里；第二版把 `见审核文档第十二节` 也判成散文，`test_cross_document_section_pointer_needs_the_file_named` 又红——于是定稿规则是：**带节号/批号/附录号的 span 一律算引用**（散文不会 accidentally 长出「第十二节」），**只带编号的 span 必须站在引用位置**（`可见…M6–M8` 里的编号只是句子里提到的另一个话题）。落地：`_POINTER` 后加 `_CITATION_HEAD`，每个标记落进 `POINTER_BOXES` 六箱之一，`Stats` 从 `unresolved: int` 换成 `markers + boxes`，总结行打印 `checked 40 of 143 「见」 markers (checked=40 citation-without-locator=15 …)`，并新增一条 `RECONCILE`：分箱之和必须等于**独立重数**的标记数 | 本批新增 6 条门（`tests/test_doc_pointers.py` 26 → 32）；全量 `.venv/Scripts/python.exe -m pytest -q -W error` 见第二十三批的承重量。**两条量到的边界，写清楚免得被当成已解决**：① `_ID` 的 `\b` 修复在今天的语料上移动的编号数是 **0**（`old=915 new=915`，全仓 19 个文档一个都没粘着中文）——这条修复现在只由合成门撑着，语料里还没有它的用例；② 「见」后面接普通散文（`见交付说明第8节`、`详见总交付第9节`、`见注释`）落在词内箱，**它确实是指针，只是这台量具查不了**：阿拉伯数字的 `第8节` 不在 `_SECTION` 的中文数字表里，而那两份文档没把文件名写进指针。此外 `可见、意见、预见、见证、见收益` 一整行只算 **1** 个标记（`、` 不终止 span，五个后缀被一次吞掉），所以词内箱的量是"标记串"不是"字数" |
| M8-T40 上一批写在「边界」里的那句「这台量具查不了」，本批结案：定位符两侧都认阿拉伯数字，两条真断言从「没人查」变成「查得过」；顺手补上链接阅读器缺的那层掩码 | ✅ | 见下方「第二十四批 M8-T40」。**先量的结论把任务改了方向**：这批原本要问 `citation-without-locator` 那 16 条能不能有判据，逐条摊开的答案是**一条都不能**——4 条指向「注记」、3 条指向表格某一格、6 条指向相对位置（本批末尾/下一行/上一条/下面这一行/下/下表）、1 条指向占位符 `第N批`（N 不是数字，判据答它就是说谎）。所以那箱维持「有名字、有条数、没有判据」。价值在词内箱：77 条里有 **2 条**是真指针（`见交付说明第8节`、`详见总交付第9节`），掉进去只因为 `_SECTION`/`_BATCH` 的数字表没有阿拉伯数字；**而这两条断言本身是真的**——落点文档的 level-2 标题自己写着 `## 8. 继续实施：第二轮边界收敛`。改法三处缺一不可：`_NUM`（散文侧认数字）、`_numeral`（原 `_cn_numeral`，改完名字不再说谎）、`_numbered_headings` 认 `^(数字|中文)[.、]`（标题侧）。启用数字后第一次实跑红 2 条——昵称不是可查文件，红是对的，于是按老规矩**改落点不放宽门**：那两行写成 `[交付说明第8节](OPTIMIZATION_DELIVERY_2026-09-18.md)` 形式，同段 line 56 早就用了这个写法。**第二条缺陷是这段记录自己撞出来的**：把链接形状写进反引号当例子，`--check` 立刻报 `DANGLING LINK … 链接目标 文件 不存在`——指针阅读器从 M8-T37 起就尊重「反引号内是引用不是断言」，链接阅读器根本没有掩码这一步；补上 `check_links` 的掩码，并留下非空守卫：语料里有 **5** 个链接形状是**被引用**的而不是被声明的（撤掉掩码，它们全被当成断言） | **四条变异**（基线 sha256：文档 `0b132c831943`、脚本 `d0e34c21f76a`；锚点强制命中 1 次、`.py` 先 `compile()` 再落盘、字节还原并复验）：M1 把 `第9节` 改成不存在的 `第17节` → `--check` exit=1，逐字 `「[总交付第17节](OPTIMIZATION_DELIVERY_2026-09-18.md)」 指向不存在的第17节`；M2 **同一个编号**换指向只有 4 节的 `GAP_ANALYSIS_AND_ROADMAP.md` → exit=1 `指向不存在的第9节`（文件名真的被咨询了，不是「哪个 md 都行」）；M3 撤掉散文侧数字分支 → `3 failed, 35 passed`；M4 只撤标题侧 → `5 failed, 33 passed`，其中包含 `test_shipped_documents_have_no_dangling_references`——**半改比不改更糟**：读得懂「第8节」却没有标题能答它，两条真断言立刻变两条假红。**还有一次红是红在量具上**：第一版 `mutate()` 用文本往返，磁盘上的 CRLF 被写成 LF，sha256 复验当场抓住；换成字节快照/字节还原后四条一致。分箱前后（在未插入本批记录的文档上量）：`checked 42→44`、`word-interior 77→75`、标记 154 不变；链接侧补掩码后 28→23 | 本批新增 6 条门（`tests/test_doc_pointers.py` 32 → 38）；全量 `.venv/Scripts/python.exe -m pytest -q -W error` 见第二十四批的承重量。定稿实测写在第二十四批末段（`--check` exit 0） |
| M8-T41 有一箱写着「另一个阅读器已经接手」，实测 7 条里 5 条根本没人接手——交接判据看的是反引号在不在，不是对方认不认那个形状 | ✅ | 见下方「第二十五批 M8-T41」。起点是上一批挂在边界里的那句「一条「见」跟两个代码片段只计 1 个标记」；先量的结果是**语料里一个都没有**（全仓 gap 带代码片段的标记总共只有 7 条），洞在更下面一层：分箱只问「gap 里有没有反引号」，于是裸文件名（`README.md`、`test_anthropic_provider.py`、`config.py:331-338` 两条）和头部不被跟踪的路径（`output/playwright/frontend-scale-metrics.json`）全被记成「证据阅读器会查」，而证据阅读器**故意**不把它们当断言——两台阅读器一台说「这不是断言」、另一台说「这不是我的事」，5 条真实断言就这样在账上算已托管 | **改法：交接要验发票。** `_gap_targets` 给 gap 里每个代码片段定形状（`evidence`／`name`／什么都不是），只有 `evidence` 才准落交接箱（语料 7→2）；`name` 进新的第七箱 `code-span-names-a-file`，由指针阅读器自己回答——带目录的按链接阅读器那套 `_holds` 问，裸名允许命中任意一个被跟踪同名文件（`config.py:331-338` 说的是位置不是导入路径，要求唯一只会教人补目录名），git 忽略的名字算生成物不算缺失，行号范围还不得超过被引文件行数。**五条变异全部落红**（脚本 sha256 `dbb05e722347`，锚点强制命中 1 次、字节快照还原复验）：退回「有反引号就算交接」→ `4 failed, 37 passed`；存在性判定留个空候选兜底 → `1 failed`；撤掉行号判定 → `1 failed`；把「形状像文件」的要求去掉（任何片段都算名字）→ `1 failed`，红在那条 `answer` 门；撤掉 gitignore 分支 → **`4 failed`**，其中 `test_shipped_documents_have_no_dangling_references` 与端到端门一起红——那条生成物豁免不是纸面上的宽容，是语料在用的判据 | 契约改动要一起改账：`_pointer_spans` 从三元组变四元组（多带 targets），三条既有门在同一提交内改；分箱从六变七，`set(floors) == set(POINTER_BOXES)` 那条门会把「只加箱不改账」当场抓住。**gap 里是代码片段但什么都不是**（一个只写着字段名的片段）既不许留在交接箱、也不许落进词内箱（那箱的含义是「根本不是引用」），落 `citation-without-locator`；这条今天语料移动 **0** 条，只由合成门撑着，照上一批的规矩写明。本批新增 3 条门（38 → 41）、定稿实测见第二十五批末段 |
| M8-T42 另一个交接箱也没验发票：判据问的是「句子里有没有方括号」，链接阅读器认的是「完整链接＋它愿意判的目标」 | ✅ | 见下方「第二十六批 M8-T42」。上一批把「别人会查」这条承诺在证据阅读器那边验了一遍，同一句话在另一个箱子里还挂着：`carried-by-link-reader` 的受理条件是一个方括号，而链接阅读器走的是 `[文字](目标)` 这条语法，并且**主动跳过**四类目标（空、页内锚点、外链、被空格打断的形状）。逐条量：语料 9 条今天全部兑付（把标记自身区域抹掉后，链接阅读器的计数会掉下来），但合成形状一探即破——`[待定]`、`[说明]()`、`[说明](a b.md)`、`[本节](#t)`、`[官网](https://…)` 五条全被记成「别人会查」，而 `check_links` 实报 `checked=0`，两台阅读器一台说「这不是我的事」、另一台说「这不值得查」。反向也错：`见下方 [说明](README.md) 一条` 这种方括号不在 span 首位的真链接，被记进「有名字没判据」那一格 | **改法：判据换成对方自己的语法，并且两张跳过表合成一份。** `_link_judged` 成为唯一副本（链接阅读器自己走它，指针侧问的也是它）——上一批那条「改一处两边同变」的教训在这里以结构而非以门的形式落地；`_pointer_box` 多收一个 `region` 参数，取**掩码后**的标记区域，于是「只在反引号里出现的链接」两边一致地看不见。**四条变异全落红**（脚本 sha256 `1a74a5f09524`，锚点强制命中、字节快照还原复验）：退回「有方括号就算托管」→ `3 failed`；交接箱永远不受理 → `5 failed`（含下限门与语料对账门）；放宽跳过表让外链也算 → `5 failed`，红法里有两条是老门（`test_relative_links_must_resolve_and_urls_are_left_alone`、端到端门），说明这条规则不是本批新门独撑；把区域换成未掩码文本 → `1 failed`，红在那条「反引号里的链接是引用不是断言」的老门 | 语料两侧各移动 **0** 条：交接箱仍 9、`citation-without-locator` 仍 16，读数 `checked 48 of 163` 与上一批逐字节相同——所以本批改的是判据的强度，不是文档的错误，这一类今天只由合成门撑着，照 M8-T40/T41 的规矩写明。**新门 3 条**（41 → 44）：五个形状的两侧同判（箱＋对方实报的 `checked`）、反向那条真链接、以及语料级对账「每个交接标记抹掉自己的区域后链接阅读器看到的链接必须变少」——后者读的是 `check_links` 的返回值，不是指针侧对同一规则的第二份拷贝，否则就成了自我满足。**边界**：被掩码护住的那条「引号里再套反引号」的形状落 `word-interior` 而非 `citation-without-locator`，因为它的 span 不以引用位置开头——那是 M8-T39 定稿的 `cited` 规则，本批不动它，写在这里而不是藏起来（形状见第二十六批的围栏块例子，围栏内容对三台阅读器都是引用不是断言） |
| M8-T43 还有一对同一想法的两份拷贝：抽取器的方位词组认十个词，判据认十七个，`见下文「X」` 这类指针从来没被抓住过 | ✅ | 见下方「第二十七批 M8-T43」。上一批的教训是「两张跳过表合成一份」，仓库里第三对漂移是 `_POINTER` 与 `_CITATION_HEAD` 各持一份方位词。先量的结果本身就是第二条发现：语料里 `见…「X」` 形状 24 条、23 条带编号已被答、恰好 1 条无人读——而**短表让这一形状在语料里表现为 0，任何「语料里有没有」的探针对它只能报 0**，两份表漂移的代价是「少了几条量不出来」。**只做语法合并会反向出错**：单测跑一遍，那条标记从「有名字没判据」的明账搬进 `word-interior`——M8-T40 已确立那格的含义是「根本不是引用」。所以抓得到、有专属格子、有阅读器答它三件事同批落地 | **第八箱 `cites-a-quoted-name`＋它自己的阅读器。** `_DIRECTION` 成为方位词唯一来源（抽取、head 判据、`_PLACE_WORD`、`_AFTER_MARKER` 四处都从它拼接）；只有 `见<方位词>「X」` 算处所引用（裸 `见「X」` 仍归 M8-T39 的 head 判据，收窄是 M8-T40 那条掩码门继续承重的前提）；新箱刻意**不进** `checked` 那个整数，让它继续只表示「定位符形状的目标被解析掉了」；判据是名字必须在**指针声称的那一侧**被声明——标题文本、`**粗体标签**`、表格行首格之一，`上*` 在前、`下*` 在后，外加一条自引守卫：包裹指针自身的那条标签不算声明。**五条变异全落红**（脚本 sha256 `8331bf727484`，锚点强制命中、字节快照还原复验）：只合并抽取、新箱永不受理 → `5 failed`；去掉自引守卫 → `1 failed`（那条守卫只有这一条门撑着）；放宽成「凡引号皆处所」→ `2 failed`，其中一条是 **M8-T40 的老掩码门**（这条规则不是新门独撑）；两份方位词表重新分叉 → `4 failed`，即本批起点；量词里多一个空格让抓取全盲 → `7 failed`，红法里最值钱的是下限门那句「harvest 到 0 条，低于下限 15」 | 语料 `citation-without-locator` 16→15、`cites-a-quoted-name` 0→1、`checked` 仍 50（移动只发生在分箱之间）。**一条真实文档缺陷随之量出**：那条指针命名的 `当前实测` 在本文档从未被声明，按 M8-T36 的口径改文档（写成粗体标签）而不是放宽判据。**本批自己踩的坑进了门**：新 docstring 里一个转义反引号是 `invalid escape sequence`，而它只在**源码被重新编译**时才是 `-W error` 下的错误——`__pycache__` 里的旧字节码让全量套件白绿了几小时，直到变异脚本重写源文件才炸。新增一条「从磁盘字节重新 compile()、warnings 升级为 error」的门。新增 6 条门（44 → 50），全量 1072 passed。**边界**：名字是子串匹配不是全等；方位词只排声明位置的前后、不读被引段落的语义；引号里带定位符的仍归定位符阅读器；一条指针同时点两样东西仍只答一半（M8-T42 边界①同一件事）；`citation-without-locator` 仍剩 15 条 |
| M8-T44 一条指针可以同时点两样东西，而第二样没人答：`结论见 README.md 第8节` 由**本文**同名节应答（README 没有任何编号二级标题），`口径见 nope.md 与 [说明](README.md)` 里那个裸名落在所有栏之外 | ✅ | 见下方「第二十八批 M8-T44」。上一批边界④记着「一条指针同时点两样东西仍只答一半」，这一批去量那一半。量法自己错了三次：200 字窗口读进同一行别的代码片段（4 条假租户）；收窄到标记自己的 `span` 得到八箱全 0——先证明量具看得见才敢把 0 当数（同一条抽取管线喂合成样本，名字照样抓得到）；只调 `check_pointers` 会把「其实有别人报了」读成假绿，因为散文路径阅读器只认带目录的名字；最后改用出货入口 `check_document`，并把六个用例从「同一个探针文件连续覆写」改成「一例一个新文件」——覆写窗口造过一条行号为 1 的节红，单独复跑同一条是绿的 | **所有权 + 裸名归位，两张判据都用同一份形状**。指针自己点名了文档，那一节就**只在该文档里解析**（`_numbered_sections` 复用 `_numbered_headings`，不另写一套「有没有第N节」）；标记 span 里的裸文件名交给 M8-T41 那套名字判据答，带目录的**刻意不重报**（散文阅读器已经为它开票，一票两处就是 M8-T41 反对的那种账）；裸文件名的形状从 `_PROSE_PATH` 拼进引用头，扩展名清单在仓库里只有一份手抄。控制组是这批的中心证据：改前「README 第8节」与「节真的在本文」两条读数**逐字段相同** | 语料**规则改动移动 0 条**：定稿 `checked 53 of 172`（这 4 个标记是这段记录自己写的），把本批的行与节删掉、走同一个出货入口重测，逐格回到 `51/168`、八箱 `[51,15,9,2,6,1,3,81]`、`red=0`，`--check` exit 0。所以这批全部重量在合成门与控制组上——「类可达、租户为 0」是量出来的事实。新增 6 条门（50 → 56），全量 1078 passed（546.86s）。**五条变异各自落回本意的门**，其中 m4（把形状手抄一份、`.pattern` 逐字相同）只红唯一副本那条门——它红不了任何行为门，这正是它要防的事；第一轮 m4 是**零证据变异**：heredoc 把 `\\b` 吃成退格符，两条行为门一起红，红的是变异自己；补上「变异文本须原样落盘且不含控制字符」自检后重跑。**边界**：所有权只覆盖 `第N节`；裸名只在标记自己的 span 里生效；`A` 组那条指针的 `checked` 至今仍是 1（文件不存在由 PROSE 报，指针栏只说自己那一半） |
| M8-T45 一条计时门的上限是机器负载的函数：同一条门在本批一个字没碰的代码上连红两次，而**上一批开出的药方（改成秒数比值）也被本批量红了** | ✅ | 见下方「第二十九批 M8-T45」。**先量的结果否掉了自己的处方**：同一份 250/1000 文件形状，未改代码的 wall 比值读到 4.64 / 4.46 / 2.09 / 4.54（四次），把 `O(n^2 log n)` 纯 CPU 扫描挂上 `_refresh`（零额外系统调用）读到 4.01 / 4.02——**变异的区间整个落在对照的抖动里**，比值上限要么须 ≥ 4.64 因而永远抓不到回归，要么天天红；每文件 `process_time` 比值（对照 0.86~1.05、变异 0.99~1.23）同样重叠，也没给它加门。承重的是另一把尺子：**每文件系统调用次数** 5.232 / 5.208、比值 0.9954，六个读数（三种条件 × 两轮）逐字节相同，包括挂了 CPU 变异的那两次 | **五新 + 一改写 + 两处同族搬家**（`tests/test_retrieval_enhanced.py` 15 → 20 条门；`test_parallel_writes_are_actually_overlapping` 早已有结构见证，那条 `elapsed < 0.6` 是冗余秒表，改判 `_max_in_flight(events) >= 2`；子代理的取消与超时**按文字可分**，判据搬到 `"[TIMEOUT]" not in result.summary`）。旧门名字保留：它是文档一处指针的落点，docstring 写清「判据的一半搬走了」。**五条变异各自落回本意的门**（详见第二十九批那张表）：m2 每文件多 stat 五次 → 红在常数上限（`assert 10.208 <= 7.0`），而**比值那一半在 0.9977 处绿着**——两种失效模式所以两条判据；m1 让计数器不再累加 → 四条红、**一条绿**，绿的正是那条「查盘 0 次」的缺席门（0 == 0），它看不见仪器坏掉 | 全量 `.venv/Scripts/python.exe -m pytest -q`（冷字节码）**1083 passed**，上一基线 1078；本批不动文档阅读器；`tests/test_doc_pointers.py` 收口时是 56 条门，M8-T47 落地后新增一条裸控制字节的门，现值 57 条（同一条记录里两处 56 的旧说法以本句为准）。定稿实测 `checked 63 of 207`（八箱 `63/15/9/2/6/2/3/107`、23 条链接、856 条证据断言、228 个受版本控制的文件、`--check` exit 0）。**边界**：纯 CPU 的二次扫描今天没有任何门看得见（本批实测），上限与比值只覆盖「文件系统调用」这一维，见下方「M8-T48 候选」；还剩两处未量的秒表，见下方「M8-T46 候选」；扫出 2 个裸控制字节，见下方「M8-T47 候选」 |

> **下一批更正（M8-T31）**：上面这个「声明写在 `result` 负载里」的落点是错的——`result` 的内容来自模型，等于让被计费的一方自己说「我已经汇总过了」。声明已改由**主机字段**承载（快照顶层 `children_rolled_up`），镜像只在主机字段为真时把它补进负载，`TaskResult` 则一律丢弃负载里夹带的这个键。 | **这个形状是被一条老门逼出来的**：第一版把声明加在 `WorkerSnapshotMirror.result()` 的输出上，立刻红在 `tests/test_task_durability.py::test_result_contract_preserves_verification_and_normalizes_both_executors`（`Left contains 1 more item: {'children_rolled_up': False}`）——那条门要求**两种执行器归一化后的结果逐键相同**，我却在进程那一侧凭空多出一个字段。改为「由汇总写进 result 负载」之后，两种执行器自然同形，门不需要被放宽一行。新门四段各挡一种漂移：(a) 声明已汇总 → 不再相加；(b) worker 只跑了父任务自己那部分 → 子树必须补进来（525）；(c) 声明能穿过 `TaskResult` 与镜像、且**没有声明的负载确实不带键**（`"children_rolled_up" not in undeclared`）并仍会汇总；(d) **AST 断言 `_reconnect_worker` 函数体里真有 `self._roll_up_tokens(...)` 调用点**——只测 helper 会让调用点自由漂移，这是 M8-T23 那条接缝门手法的第二次使用。**测试自身的假绿也被抓一次**：第一版忘了把子任务注册进 `manager.tasks`，(a) 段就以「谁都没汇总」的姿态通过。**承重量**：忽略声明 → `assert 925 == 525`；把声明放回镜像输出 → 老契约门红；删调用点 → 红在 `['_monitor_worker', '_persist_task', '_release_session_slot']`。**同时回头更正记录**：M8-T24 那句「这条支路不汇总」就地改成「已由 M8-T30 关闭」并写清关法——过期却不改的边界句，读起来和还在的缺口一模一样。全量 **1002 passed** |
| M8-T20 配置面另一半：旋钮拧得动，但没人查得到它存在（文档漂移） | ✅ | M8-T18 自己就是触发者：这一批新加的两个键先只写进了 `config.py`，`minicc.config.example` 一字未提——**「可达」有两半，能被读到和能被查到是两件事**。于是把第二半也做成门：扫 `config.py` 里出现的每个 `"MINICC_*"` 字面量，要求它同时出现在 `minicc.config.example` 中，并带读取面下限（键数 ≥30，防正则失效后对着空清单假绿）。**门第一次运行报出 17/37 个键从未被文档提到**，其中全是真实用户开关：`MINICC_HOME`、`MINICC_SANDBOX` / `_IMAGE`、`MINICC_TASK_EXECUTOR`、`MINICC_MAX_CONCURRENT_TASKS`、`MINICC_CONTEXT_WINDOW_TOKENS` / `MINICC_COMPACT_THRESHOLD`、`MINICC_SOFT_MAX_TOKENS` / `_DURATION_SECONDS`、`MINICC_SUBAGENT_WRITABLE` / `_MAX_DEPTH` / `_MAX_TOKENS`、`MINICC_FALLBACK_MODELS`、`MINICC_AUTO_RESUME_ON_START`、`MINICC_TASK_HISTORY_LIMIT` / `_MAX_AGE_DAYS`、`MINICC_ALLOW_PRIVATE_MCP`。17 条**逐条回到代码里读语义再写文档**（默认值与夹紧取自 `load_config` 原文：并发 1..64、历史 1..200 条 / 1..3650 天、子代理深度 1..2；`_optional_positive_*` 的「留空/0/off/unlimited/非正数＝不设」而不是「报错」；`soft_max_*` 只经 `Budget.soft_limit_hit()` 提示收尾、**永不中止任务**；`prune()` 只删已终结快照，排队/运行中永不清理），写完 37/37 覆盖、清单可空。**故意不扩到全包**：`minicc/**/*.py` 另有 7 个开发者开关（`MINICC_FAKE_PROVIDER`、`MINICC_FAKE_PROVIDER_FAULTS`、`MINICC_EVAL_GRADER_DIR`、`MINICC_HOOKS`、`MINICC_KEEP_WORKER_CONFIG`、`MINICC_PRICING_JSON`、`MINICC_ANTHROPIC_MAX_TOKENS`）不属于用户示例文件，门的作用域就停在 `config.py` 这个用户面边界 | `tests/test_config_surface.py` 2 → 4 条（AST 门 + 读取面下限 + 文档门 + 文档扫描下限）。**双向红→绿都量过**：把新加的 2 个键从示例文件里删掉 → 报 `MINICC_ANTHROPIC_BASE_URL；MINICC_MAX_COMPLETION_CONTINUES`；给一个尚未文档化的键补上文档 → 当时的「只缩不涨」版本立刻报 `请把它们从 _UNDOCUMENTED_KEYS 删掉：MINICC_HOME`（这条测的是清单会腐烂，比「新键必须写文档」更容易被漏掉）。`tests/test_config_surface.py` + `tests/test_project_config.py` **22 passed**，`-W error` |
| M8-T21 配置面第三半：字段挂着，但没有任何配置层会给它赋值（`timeout` 一直只有 CLI 能改） | ✅ | 前两批分别查「读处有没有这个字段」和「文档有没有提到这个键」，这次反过来查 **字段有没有人写**：AST 取 `config.py` 里 `Config(...)` 构造的关键字集合，要求覆盖 `dataclasses.fields(Config)`，另加 `>= 30` 防空扫描假绿。**门报出一个真缺陷**：`timeout` 是 `Config` 字段、被 5 处 HTTP 调用读走（`main.py:619/627`、`web.py:1000/1170/1415`），但 `load_config` 从不解析它——仓库里既没有 `MINICC_TIMEOUT`，`config.json` 里也没有 `timeout` 键，唯一入口是 CLI 的 `--timeout`。按运行方式分组看后果：交互 CLI 能改；**Web 工作台（`web.py:2489` 裸调 `load_config`）和它派生的每个 task worker（`task_worker.py:53` 同样裸调）永远锁在编译期默认 180s**，而慢推理网关上一次非流式请求就可能超过它，用户无从调整。修法与 M8-T18 同型：`MINICC_TIMEOUT` env + `timeout` 文件键走同一个 `pick`，非数字与非正数抛 `ConfigError`，上界夹 3600s（`1e9` 这类笔误会把「超时保护」变成「永久挂起」），`--timeout` 也收到同一上界以免两条路口径不一 | `tests/test_config_surface.py` 4 → 6 条（字段可达门 + 构造扫描下限），`tests/test_project_config.py` 20 → 25（三层可达、`several/0/-5/inf/nan` 参数化报错、`999999 → 3600`）。**红→绿是摘掉构造里的 `timeout=timeout,` 量的**：门与两条 timeout 测试同时红（`3 failed, 28 passed`），接回即绿。**这条门的边界要说清**：它查的是「字段完全没进构造」，不查「进了构造但值是常量」——`max_turns` 属于后者（`load_config` 里恒为 `None`，是刻意的 legacy 忽略，见 `config.py:331-338` 注释，CLI 保留显式逃生口），因此 `max_duration_seconds` / `max_tool_calls` 与它一起进了 `_CONSTANT_FIELDS` 例外表；把例外写成表而不是把门调松，是为了让「谁在豁免」可审 |
| M8-T22 配置面第四格：用户写进 `config.json` 的键如果没有任何一处读取，全程零输出 | ✅ | 前三格尺子（读处有字段 / 文档有键 / 字段有人写）都站在**开发者**一侧；用户这一侧的同一件事是「我把旋钮写进了配置文件，它没生效，也没人告诉我」。`config.py` 的文档字符串本来承诺 *"nothing silently defaults when the user explicitly set something"*——对**坏值**成立（每个键都有 `ConfigError`），对**坏键名**不成立：`{"max_truns": 40}`、`{"compact_threshhold": 100}`、已废弃的 `max_turns` 全部静默按默认值跑完。**量化发现**：AST 扫 `config.py` 的 34 个 `pick()` 调用点，33 个满足 `MINICC_X ↔ 裸键 x ↔ Config 字段 x`，唯一例外是 `MINICC_SANDBOX` 的裸键 `sandbox`（字段叫 `sandbox_mode`）；而 `sandbox` 这个拼法在全仓库只出现在 `tests/test_core.py:24` 的 fixture 里，**那条测试断言了 api_key/base_url/model/yolo 却从未断言 sandbox_mode**——「这个键有覆盖」的错觉正来自一行没人读的 fixture（已补断言）。修法是把静默换成一次可核对的报告：① `pick()` 记下自己真正查过的每个键名（env 名 + 裸键 + 别名），词表来自解析器的**实际行为**而不是手抄清单，新增旋钮不必记得登记；② 解析全部完成后比对两层 `config.json`，未识别键逐条 WARNING，区分「用户配置 / 项目配置」并给路径，`difflib` 建议的 cutoff 定在 0.78（0.62 会把 `MINICC_LOG_LEVEL` 建议成 `MINICC_MODEL`，一条没人能照做的提示）；③ 结果同时挂到 `Config.unrecognized_config_keys` 与 `describe()` 的 `ignored_keys=`，`--print-config` 那一路也看得见；④ 三个刻意恒为不限的硬预算键走**单独的说明**（「已废弃，要收尾提示请用 `MINICC_SOFT_MAX_*`」），而不是给一个已经没人读的键猜拼写；⑤ `MINICC_SANDBOX` 补 `sandbox_mode` 第二拼法（两种都认，`sandbox` 优先），示例文件同步。**边界**：`.env` 不做这项审计（它合法地装着 `PATH` 之类的无关变量），豁免清单另有一条门守着——被停在这里的键必须**确实不经过 `config.py` 解析**，否则「MINICC_LOG_LEVEL 其实已经接进 resolver 了」这种漂移会立刻报红 | `tests/test_config_surface.py` 6 → 43 条（AST 词表扫描 + `_resolver_env_names()` 下限 25 + 豁免清单合法性 + 参数化「示例文件里每个旋钮的两种拼法都可写」，每条 payload 都塞一个哨兵键 `zz_not_a_config_key` 并断言它是**唯一**被报出的键——否则 `unrecognized == ()` 会被一个坏掉的报告器永远满足）；`tests/test_project_config.py` 25 → 31 条（用户层/项目层各报各的、废弃键给理由不给猜测、两种拼法、`.env` 保持静默、`describe()` 可见）。**红→绿**：把 `_unrecognized_layer_keys` 短路成 `return []` → 4 条红（stray / retired / 项目层 / print-config），另 3 条按构造仍绿（它们防的是假阳性那一侧，不是报告本身）。**真机**：`.venv/Scripts/minicc.exe --print-config` 配一份含 `max_truns` / `compact_threshhold` / `sandbox_mode` 的 `config.json` → stderr 两条 WARNING（第二条带「是否想写 'compact_threshold'？」），`sandbox_mode` 不再被误报，stdout 两行协议输出干净、尾行 `ignored_keys=compact_threshhold,max_truns` |
| M8-T23 `metrics` 的「不可能不同意」拿去真跑：批任务合并接缝断裂 + 双计 + 恒真断言 + 标签说谎 | ✅ | 见下方「第十批 M8-T23」。**四条互相独立**：① `task_manager.py:1679` 传 `model=parent.model`，`AgentService.merge_batch` 从没接受它 → **凡子任务全成功的并行批都在合并步死掉**（`批任务 watcher 失败: TypeError`），README 里还留着 `POST /api/tasks/batch` 示例；982 测试全绿是因为两半边各对着不像对方的替身测（批测试的 fake service 没有 `merge_batch`，`hasattr` 守卫整段跳过；`merge_batch` 测试用不绑定的 `AgentService.merge_batch(SimpleNamespace)` 假 self），修好签名后那条老测试反而红——它必须换成真 service。② 父任务快照本已汇总子任务用量，`metrics()` 却逐行相加 → 同一批调用记两次（离线实测 1315 vs 逐行 2405，+83%）；改为「每棵子树只在根上记一次」+ `subtask_rows` 可见，并反向补 `_roll_up_children()` 让自动编排那一支不再**少记**。③ `test_metrics_endpoint_reconciles_with_task_snapshots` 的成本断言两边都是 `0.0`（`test-model` 未计价 → `cost_usd=None`，而 `priced+unpriced==2` 把「全部未计价」算通过）→ 挂 `MINICC_PRICING_JSON` 才第一次比非零数。④ 不带 `?workspace=` 的 `/api/metrics` 累加所有工作区却把 `workspace_path` 填成服务自己的目录 → `workspace_path: null` + 新增 `scope` | 新增 `tests/test_batch_wiring.py` 5 条：AST 扫 `task_manager.py` 每个 `self.service.X(...)` 并用 `inspect.signature` 对**真实** `AgentService` 方法 bind（防的是整类「接缝两侧各自正确」的漂移，不只有 `model` 这一个参数；带 `_MIN_CALL_SITES=2` 与接缝名下限防空清单假绿；`_run_chat` 那处 `**kwargs` 动态调用显式跳过并说明）；批任务经真实 `AgentService` 跑到 `completed`；`merge_batch` 的 `model`/`provider_type` 落到 provider 构造参数；`metrics` 对批任务只记一次。**红→绿逐字**：`task_manager.py:1679 calls self.service.merge_batch(..., model, ...): got an unexpected keyword argument 'model'`。把 `merge_batch` 里第三份手写 provider 构造抽成 `AgentService._make_provider()`（此前合并器既不认 `MINICC_FAKE_PROVIDER` 也无法端到端测，也不认 `provider_type=anthropic`）。**真机（阶跃 `step-3.7-flash` 经 HTTP）**：批 `completed`、父 rolled-up `total_tokens=50323`、`cost_usd=null`（未计价不当 0）、`/api/metrics` 报 `task_count=23 / subtask_rows=4 / usage.total_tokens=50323`，与只读 SQLite 复核逐字节相等（逐行求和会到 99688）。**探针自身的坑**：第一趟 8791 端口早有别的进程在听，我 spawn 的服务因端口占用退出，`/api/health` 200 被误当成「我的代码在应答」→ 那趟 TypeError 是**假归因**；第二趟加了两道闸（先 bind 证明端口空、再用新字段 `subtask_rows` 做应答者身份探测）。**边界**：父任务被取消/崩溃时子任务用量仍只在子行，`metrics()` 排除子行会少记——口径未定（被丢弃的一次性任务算不算用户可见成本），不在修 TypeError 的同一次改动里替用户决定。**（这条边界已在 M8-T24 关闭，见下一行）** 全量 **987 passed** |
| M8-T24 把「父任务拥有整棵子树」做成四条终态路径都成立的事实：一处汇总、幂等、五视图同一个数 | ✅ | 见下方「第十一批 M8-T24」。M8-T23 只让**合并成功**那一条路汇总，剩下的三条（子任务失败、父任务被取消、watcher 抛错）各自把子任务真花掉的 token 丢在聚合之外。量法：把汇总抽成 `TaskManager._roll_up_tokens()` 单一收敛点，然后**逐条把它的调用点删掉**看有几条测试变红。发现：① 汇总必须发生在 `apply_result` **之后**而不是把数塞进结果负载——被取消的父任务 `apply_result` 会因终态门槛整段拒绝负载，塞在负载里的汇总跟着一起被丢掉（实测：合并器抛错时父任务 `tokens_used == {}`，1090 tokens 从 `/api/metrics` 消失）；② `snapshot()` 末尾 `output.update(result_payload)` 会用结果里的 `tokens_used` **盖掉**记录字段，于是同一时刻用户看快照是 225、聚合看索引是 1315（差 5.8 倍），修法两处：汇总时同步写回 `result["tokens_used"]`，并把 `tokens_used`/`cost_usd` 一起加进 `snapshot()` 已有的「主机维护的字段不接受负载覆写」保护块；③ 新字段必须能往返：`children_rolled_up` 进 `snapshot()` 也进 `from_snapshot()`，否则重启后恢复的父任务下一次收尾会**再汇总一次**（实测 1315 → 2405）；④ 顺带撞出来的独立缺陷：`TaskResult.to_payload()` 永远带 `tokens_used` 键，生产者没填时它是 `{}`，而 `apply_result` 把「键存在」当成权威 → 逐轮上报过 500 tokens 的运行被最后一步清零。改成**空 = 没有信息**（与 `cache_summary` 已有的 missing ≠ 0 同一条原则），全零负载不再覆盖非零记录，非零负载仍然权威 | 新增 6 条到 `tests/test_batch_wiring.py`（5 → 11）：合并器抛错 / 一个子任务失败 / 父任务在合并期间被取消 / 自动编排的父任务在侦察后崩溃 —— 四条终态形状各自断言「父任务 == 子树之和」且聚合 `cost_usd > 0`；幂等（`_roll_up_tokens` 连调两次数字不动）；**五视图一致**（快照、索引摘要、`/api/metrics`、落盘行、落盘行的 result 负载必须同为「子任务之和 + 合并自身」，ground truth 用合并返回前的用量快照独立算出来）；重启不再汇总（`from_snapshot` + 再调一次）。`tests/test_core_task.py` +1 条守④。**红→绿逐字**：删 except 路径的汇总 → `assert 0 == 1090`；删幂等门槛 → `1315 → 3495`；删 result 同步 → `{"snapshot": 225, "summary": 1315, "metrics": 1315, "persisted": 225, "persisted_result": 225}`（五个视图分裂成两个数）；删 `from_snapshot` 那行 → `assert 2405 == 1315`；删 watcher 成功路径的汇总 → 5 条同时红。**测试自身撞出的第二个坑**：`_wait(service, id)` 以「状态进入终态」为返回条件，但取消是**从 watcher 外面**把状态变终态的，汇总发生在合并器返回之后 → 首读会拿到 `{}`（这条竞态在空载下不复现、全量负载下必现），补 `_wait_billed`；同理 SQLite 行是 write-behind 镜像，最后一次强制落盘在状态之后，故落盘视图改用 `_wait_row` 轮询镜像追上再比。**边界**：被取消那次合并**自己**花的 100 tokens 不归属（终态门槛整体拒绝负载，测试记录这一事实而不是改动状态机语义）；`WorkerDetached` / `_reconnect_worker` 那条支路当时**也**不汇总（这条边界已由 M8-T30 关闭；关法不是「那里也加一次」，而是让汇总过的负载自己声明，见该批记录）。**真机（阶跃 `step-3.7-flash`，一条只读两子任务批）**：子 `9178+7186=16364`、父 `16884`，快照 / 索引摘要 / 落盘行 / 落盘行的 result **四个视图逐字节相同**，只读 SQL 在工作区与全仓库两个口径上都与 `/api/metrics` 相等（`67207 == 67207`；逐行相加会多算 `65729`），`from_snapshot()` 重建后再汇总一次是 `16884 → 16884`；真实网关才送的 `prompt_cache_*` 走的也是这条加法。顺带撞出「未计价时单任务报 `null`、聚合报 `0.0`」这条新的撒谎字段 → 记在下一行 M8-T25。全量 **994 passed** |
| M8-T25 `/api/metrics` 的总额在**全部**未计价时报 `0.0`，同一份 payload 里别处报 `null` | ✅ | 见下方「第十二批 M8-T25」。真机复核（M8-T24 那趟）撞出来的第三条撒谎字段：父任务快照 `cost_usd=null`、`by_model.<未计价模型>.cost_usd=null`，而顶层总额 `cost_usd=0.0` —— **同一个响应同时说「不知道」和「没花钱」**。`by_model` 那侧早就按 `priced` 标志把不可知的桶置 `None` 了，总额只是漏掉了同一条规矩，所以「哪个约定是对的」不需要问客户端，仓库自己已经答过一次 | 修法两条：`priced_tasks == 0 → cost_usd: null`；部分计价时保留数字（它就是已计价那部分的小计）但新增 `cost_is_partial` 明说它不完整。**原先挂起的「口径」问题被这样消解**：下界与总额之争其实不必二选一，字段含义不变、完整性单独用布尔说出来。**红→绿逐字**：把总额改回 `round(cost_total, 6)` → `assert 0.0 is None`。**门自己抓到我一次错**：`cost_is_partial` 第一版写成 `bool(unpriced_tasks)`，在全未计价那格是 `True`——「一个都不知道的数是部分已知」这句话本身不成立，是新写的 (a) 段断言当场把它判红的，正确定义是 `priced_tasks and unpriced_tasks`。**行为变更要如实记下**：`cost_usd` 从「恒为数字」变成「可能是 `null`」，对假设 float 的客户端是破坏性改动；`grep` 全仓库确认 `/api/metrics` 只有 `webserver.py:324` 一个入口、HTML/JS 里没有任何消费者，README 已把三种取值写清；读取侧的测试只有 `tests/test_logging.py` 与 `tests/test_batch_wiring.py` 两处（都给了定价，因此除新门那格外不受影响）。**边界**：`priced_tasks`/`unpriced_tasks` 现在数的是**根任务行**（子任务已汇总进父行），所以三格相加等于 `task_count` 而不是任务索引总行数——`subtask_rows` 已经在那里说明差额 |

### M1-M3 退出标准真跑记录（第一批，2026-09-22）

按第三节原文逐条执行，不走附录 D 的自评：

| 标准 | 结论 | 证据 |
| --- | --- | --- |
| M1-1 `pytest -q` 全绿 | ✅（Windows 这条腿） | 最新基线 `.venv` 全量 **1044 passed**（`-W error`，exit 0；上一基线 1035、1018、1002、999、998、997、995、994、987、982。中间点 1006→1011→1018→1035→1044（1018→1035 是 M8-T36 的 17 条门、1035→1044 是 M8-T37 的 9 条门，两步差额都恰好等于新增门数，实测）：**M8-T34 那一批只留了文件内数字**（`test_http_route_inventory.py` 9 passed、与 `test_http_surface.py` 合计 86 passed），没有跑全量，所以 1011 这一格是**推出来的而不是量出来的**，写在这里而不是当作实测）。**破 1000 条不是成就本身**——这一千里有围栏（M8-T27）、有把规则边界逐名列成数据的门（M8-T29 的 11+10 名单）、有专门盯调用点的 AST 门（M8-T30）、还有一批专门守量具本身的门（M8-T35），它们不新增产品能力，只是让「已承诺的行为」变得可以被机器复查；这条要记的是**口径**而不是规模。wall time 这一列同命令测量：**222.92s**（994）、**230.90s**（994 复跑）、**339.84s**（995）、**245.65s**（997）、**306.94s**（998）、**226.26s**（999）、**411.10s**（1001）、**305.85s**（1002）、**212.48s**（1006）、**266.32s**（1018）、**245.16s**（1035）、**217.20s**（1044），更早还有 238.58s / 280.65s / 518.39s——**212-411s 之间摆动，而 1001 次比 999 次只多 2 条却慢了近 8 分钟**，所以时长口径本身不可信。**M8-T35 这一趟顺手量了「本机到底有几个测试进程」，并且当场纠正了自己一次误判**：第一版结论写成「同仓库另有 6 个并行 run」，来源是 `Get-CimInstance … | Format-Table -Wrap` 的输出被 `grep -c pytest` 数行——`Format-Table` 会在 ~118 列折行，一条长命令行被拆成好几行，而那些长命令里**有我自己这批派生的子进程**（`route_coverage.py --check` 会 spawn `coverage run … -m pytest tests/test_http_surface.py … -q`，尾部恰好长得像 `-m pytest -q`；`test_worker_survives_host_crash_and_continues_long_stream` 的临时目录也来自我自己这一趟跑 `tests/test_task_worker.py`）。按 PID + 创建时间 + 完整命令行重新归因之后，能确证的只有：**另一个项目的 `pytest tests/unit -m "not integration"` 在同窗口活跃**；**同仓库是否有并行 run 未证实**（我派生的嵌套 pytest 让初版数字虚高）。**教训与本轮主题同源**：一个把「表格折行的行数」当成「进程数」的数法，和第十七批那个把「共享前缀的字符串」当成「路由被覆盖」的判据是同一类错误——**归因要用能区分个体的字段（PID/时间戳/完整命令），不能用计数代理**。这次 266.32s 仍**不归因于条数**；结论不变：**测试条数与 exit code 是口径，wall time 只用来记「这次跑了多久」**。共享 `~/.minicc/tasks.sqlite3` 的测试要在安静时段复跑才算干净基线（M8-T37 那一趟 1044/1044 通过、没有因争用而失败的用例，但「没失败」不等于「没被干扰」）。**M8-T37 把那句教训落成了一次复查**（按 PID + 完整命令行归因，不按 `grep -c` 行数）：那一趟跑完立刻看本机进程，5 个 python 里 4 个是 pytest，命令行分别是 specproof-reference 的 `tests/unit tests/security tests/fault`、某工作区的 `toycalc_test.py`（各两进程，父子各半）与一个占用 8731 端口的 uvicorn——**没有一个命令行里出现 minicc-codex**，所以「本仓库没有并行 run」这次是量出来的而不是假设的；代价要说清：只在结束时刻复查过一次，不构成「整趟期间都没有并行」。Ubuntu 那条腿本机不可用，只有 CI 能证，**不在此声明** |
| M1-2 `scripts/reliability_probe.py` 一键复现、退出码 0 | ✅ | 真跑：9 个 M1 target 全绿，`exit=0` |
| M1-3 人工核查（只认 text delta 与 `[DONE]`、空答案不算成功） | ✅（**查出并修掉一条真实缺陷**） | 三条子判据分别处理。**① 只认 text delta**：两条协议分支各自独立核过——`chat_completions` 分支里 `delta.content` 与 `delta.reasoning_content` 走**两个不同的 assembler**，reasoning 永远进不了 `committed_text`（`openai_provider.py:1017-1040`）；`responses` 分支只消费 `response.output_text.delta` 一种事件类型，其余事件不产生可见文本（`:784-791`）。**② 假网关只发 delta + `[DONE]`、从不发 finish_reason**：这条原本写着「人工核查」，其实**可以在 wire 上执行**，新测试用 `httpx.MockTransport` 返回真实 SSE 字节（一条 content delta + `data: [DONE]`，无 finish_reason），断言 **HTTP 请求恰好 1 次**（不是 5 次重放）、`run_agent` 以 `LLM 调用失败: stream ended before completion` 明确结束、且已经流出去的「半句话」保留在 answer 里。顺带纠正一处口径：旧测试 `test_m1t5_stream_without_finish_reason_fails_fast` 数的「1 次」是**被打桩的 `_create` 调用次数**，不是 HTTP 请求数。`[DONE]` 在 openai 路径由 SDK 自己消化，仓库里唯一手写 SSE 解析的是 anthropic 路径（`anthropic_provider.py:372` 对 `[DONE]` 有防护）。**③ 空答案不算成功 → 此前不成立**：`loop.py` 有两个交付点写 `result.answer = text or "(模型返回空回复)"` 而 `result.error` 保持为空，也就是**一轮既无内容又无工具调用的完成会被当作成功交付**，且此前没有任何测试引用过那个占位串（grep 全仓库只命中 loop.py 自己）。两处都改成显式失败（`code="empty_answer"`，answer 写成「任务未完成：…」）。保留的判断：`text` 为空时仍会先取 `reasoning_content`（`:1409-1411`），部分模型只把答案写在推理段里，所以「空答案」的判据是**两者都空** | `tests/test_m1_integrity.py` 15 → **17**：`test_m1t3_delta_only_gateway_costs_one_request_and_errors`（wire 级，修复前后均绿——它验证的是已经成立的部分）、`test_m1t3_an_empty_final_answer_is_not_reported_as_success`（**先红**：`assert None` 于 `TurnResult(answer='(模型返回空回复)'…)`；改完转绿）。全量 `-W error` **913 passed / 233.81s**，语义变更未打破任何既有交付契约 |
| M1-4 golden delta 序列：streamed text 必须与 answer 一致 | ✅（今天才真正成立） | 判据落在 M8-T13 的两条新测试（增量逐字到达 surface；`StreamWriter.matches`）+ `visible-equals-stored` 真机 3/3。**此前这条标准是靠终端肉眼看的**，实际一直在丢字 |
| M2-1 / M2-2 四份安全测试文件全绿 | ✅ | `test_web_security + test_permission_modes + test_allowlist + test_file_tree_api + test_security_perimeter + test_task_durability` 共 **63 passed** |
| M3-1 Origin/CSRF 与会话持久化全绿 | ✅ | 同上（含 `test_web_security`、`test_task_durability`） |
| M3-3 `grep -rn sk-` 在 `.minicc/` 与日志里零命中 | ❌ **标准本身不成立** | 仓库自身 `.minicc/web-8765.stdout.log` 命中 **19,167 次**，全部是 **`task-<hex>` 里含子串 `sk-`**（真实密钥字符串不在其中、文件 gitignored 且 mtime 早于 M1 开工一个月）。和 M8-T5 的 `git grep -c 'print('` 同一类：**字面 grep 口径不可信**。 |

M3-3 的处理不是把标准删掉，而是把它变成可执行、可证伪的门：`scripts/reliability_probe.py` 现在多跑一段
`scan_credentials()`，只认真正的凭据形状（`\bsk-[A-Za-z0-9_-]{20,}`、AKIA、PEM 头、`.env` 里那把 key 的原文），
**只报文件路径与规则名、绝不打印命中内容**（PEM 字面量在脚本里拼接，避免本仓库自己的 pre-commit 钩子把它当泄漏）。
验证：真实状态目录 0 命中 `exit=0`；把一条长 `sk-…` 和一条 `AKIA…` 放进临时目录后 **2 命中、`exit=1`**（先红后绿做完再删临时文件）。
### M4 退出标准真跑记录（第二批，2026-09-22）—— 含一条**未达成**

| 标准 | 结论 | 证据 |
| --- | --- | --- |
| M4-4 `benchmarks --suite v2` 的 `grading_coverage=1.0`、分母 ≥24、edit 类 ≥10 | ✅ | 真跑 `--suite v2`（不 `--run`）：`fixture_count=24`、`grading_coverage=1.0`、按类 `write 12 / multi-file 6 / test-fix 6`（edit 类 12 ≥10）；`pass_at_1=None`（未运行，符合「not_run 既不算通过也不算失败」的注记） |
| M4-5 A/B gate 违规时 exit code 1 | ✅ | 同一份结果 `--gate pass_at_1>=0.5 --gate grading_coverage>=1.0` → **exit 0**；把 variant 换成未运行那份（`pass_at_1=None`）→ **exit 1 + `[GATE FAILED] pass_at_1>=0.5 实际=None`**。两个方向都验；且它把 None 当 None（`不可计算（None，而非 0）`），不拿 0 冒充结论 |
| M4-6 未知模型 `cost_usd=None` 且 `cost_available` 如实 | ✅（真机 2 条） | `--run --max-tasks 2` 真跑：`cost_available=0`、逐任务 `cost_usd=None`、`token_usage_available=2`，同时 `latency_p50_ms=66695.5 / p95=120182.05 / tokens_per_success=179683` 都有值 |
| M4-7 `pytest -q -W error` 全绿 | ✅（2026-09-22 修复后复测） | 曾失败：`python -m pytest tests/ -q -W error` → **2 failed, 878 passed**：`tests/test_task_worker.py::test_manager_process_mode_runs_task_in_subprocess`、`::test_worker_survives_host_restart_and_continues_long_stream`，均为 `ResourceWarning: subprocess NNNN is still running`（`subprocess.Popen.__del__` 经 pytest 的 unraisable hook 升级为错误）。修复后复测：`.venv` 下 `pytest -q -W error` → **904 passed / 0 failed**（893 + packaging 11；149s + 13s）。同一条标准还要求「PR 门禁 ≤15 分钟」——实测 149s ✅ |
| M4-2 `npm run test:web` 离线基线 | ✅（照标准原文跑通） | 起 `minicc-web --port 8791` 且 `MINICC_FAKE_PROVIDER=1 MINICC_BASE_URL=http://127.0.0.1:9/v1`（不可达），再 `MINICC_WEB_URL=http://127.0.0.1:8791 npm run test:web` → **exit 0**、`web smoke passed: timeline, product path, desktop, mobile`。标准文本漏了前置条件：这条**必须先起服务**（脚本读 `MINICC_WEB_URL`，默认 8765），不起服务时它是 navigation 失败而不是退出码 0 |
| M4-1 证据链回归 | ✅ | `test_m4_evidence_chain + test_verifier_lifecycle + test_verification_command_variants + test_http_surface + test_mcp_stdio + test_mcp_http` 共 **98 passed**（`test_mcp_stdio.py` 11 个测试函数 ≥ 标准要求的 8） |
| M4-3 rpc 分派器 ≥10 method 有测试 | ✅（2026-09-22 补齐后复测） | 曾不成立：分派表 `minicc/web.py:238-246` 只有 **5 个 method**（`thread/start`、`thread/read`、`turn/start`、`turn/read`、`turn/interrupt`）+ `initialize` 内建。现在补了 5 个只读检查 method（`workspace/read`、`models/list`、`changes/read`、`sessions/list`、`permissions/read`），合计 **10 个可注册 method**（`initialize` 另计），每个一条测试、共用同一套 `workspace_roots` 越界校验，并由 `test_rpc_dispatcher_exposes_ten_methods` 把「≥10」变成可执行断言而不是文档口径 |
| M4-3 `POST /api/*` 由 Python 测试覆盖 100% | ✅（按实测口径改写，2026-09-22） | 原写法不可执行：`pytest-cov`/`coverage` 都未安装、CI 不跑覆盖率，「100%」这个百分比在本环境**算不出来**，不能声称。按决策改成可执行清单门 `tests/test_http_surface.py::test_every_api_route_is_named_by_a_python_test`：用 AST 从 `minicc/webserver.py` 的 `do_GET/do_POST/do_PUT/do_PATCH/do_DELETE` 里抽出服务器自己比较的路径字面量（实测 **28 条**，含审计点名的 6 条），逐条要求在 `tests/*.py` 里出现；另有 `>=25` 的下限，防止将来路由换一种写法后清单变空、门变成**假绿**。反方向也验过：喂给 walker 两条合成新路由，门立刻点名。诚实边界：这条门证明「这条路由有测试提到它」，不证明「有真请求打到它并断言终态」——后者仍由本文件里那批 `_LiveServer` 契约测试承担。**2026-09-23 再进一格（M8-T32）**：现在有一个门把「路由表里每一条」真的发一次请求打过去（GET 17 条 / POST 12 条），要求「要么答，要么带稳定 code 地拒」，并打印实测比例 100%（口径见下方 M8-T32，仍不是行覆盖率）。**2026-09-23 第三格：那个「算不出来」的百分比现在算出来了，而且是真的**——把 `coverage[toml]` 声明进 dev extra（`pyproject.toml` 的 `[project.optional-dependencies].dev` + `[tool.coverage.*]`），于是「本环境没有覆盖率工具」这句话不再成立。实测口径写在 `pyproject.toml` 的注释里：`coverage run --source=minicc.webserver -m pytest tests/test_http_surface.py tests/test_http_route_inventory.py`，然后 `coverage report --include="*webserver*"`。两个数分开报，因为它们回答不同问题：**① 模块行覆盖 74.5%**（494 语句 126 未执行，差额是错误分支、SSE 内部与 404 兜底）；**② 分派点覆盖 GET 20/20、POST 14/14 = 100%**（用 AST 取每条路由自己的比较语句行号，再问覆盖率 JSON 这行有没有执行过）。**M4-3 的标准说的是②**，所以这条按 100% 成立；①不冒充②。`pip check` 通过，说明新依赖声明完整（此前 httpx 就是靠这条纪律补上的）。**同日更晚（M8-T35）把「口径可复现」这句话本身拿去量，量出两个缺陷**：(a) ② 的算法只存在于仓库外的临时脚本（硬编码绝对路径，`coverage json` 那一步仓库里没有任何地方提到），干净检出重算不出来——仓库里写的那两条命令只能得到 ①；(b) 更要紧的是 **② 的定义可以被一次请求喂满**：`do_GET`/`do_POST` 是「一串 `if path == ...: return`」的平铺链，任何一条走到链尾的请求都会让链上所有比较行「执行过」——实测 `POST /api/nope` **一条**请求就得到 POST 侧 14/14 = 100%，而真正进入过任何分支体的是 **0/14**。② 已换成**进入覆盖**（该分支体内至少一行跑过）并落进仓库：`python scripts/route_coverage.py --check` 同时报「比较行跑过」与「分支体进过」两个数、只对后者判红。换口径后数字不变：**GET 20/20、POST 14/14 两侧在两个口径上都成立**，所以这条不是被推翻，是证据从撑不住的那种换成了撑得住的那种 |

`-W error` 那条失败的性质（下一步要定的设计问题，不是简单的测试脏）：`task_manager.py:1824-1826` 的
`_monitor_worker` 在 `self._closing` 时直接 `raise WorkerDetached()`，**既不 terminate 也不保留 `Popen` 引用**，
于是子进程活着而句柄被 GC → `ResourceWarning`。这正是「宿主关闭时把 worker 脱管交给 auto-resume」的既定语义，
但实现上留下两个后果：(1) 解释器关闭期抛 unraisable 警告（任何开 `-W error` 的门禁都会红）；
(2) 关掉宿主真的会留下孤儿进程。修法有两种、语义不同，需要产品决策：**A** 关闭时先写 cancel 标志、有界等待
（例如 ≤5s）后再 terminate，把「脱管」限定给真正的崩溃恢复；**B** 保留 `self._worker_processes` 注册表并在
shutdown 末尾统一 reap（不改变「让它继续跑完」的语义，只消掉警告与句柄泄漏）。A 改变可观察行为（正在跑的任务
会被中止），B 不改。

**决策：A**（2026-09-22 由用户选定，已实施，见第四批第 1、5 行）。取舍点是「用户关掉宿主之后，谁替这批正在烧
token 的 worker 负责」——A 让干净关闭成为真正的停止，代价是崩溃恢复与关闭恢复不再是同一套语义，因此那条契约测试
必须改写成真崩溃模拟（第四批第 5 行）。
### M5-M7 退出标准真跑记录（第三批，2026-09-22）

| 标准 | 结论 | 证据 |
| --- | --- | --- |
| M5-1 MCP stdio ≥8 个回归 | ✅ | `tests/test_mcp_stdio.py` 有 **11** 个测试函数，与 `test_mcp_http`/`test_http_surface` 等一起 98 passed |
| M5-2 巨量输出截断 / string id 回传 / stdout 不可解码时快速失败 / dead 服务 | ✅ | 逐条点名可查：`test_half_million_char_output_is_truncated`、`test_small_output_not_truncated`、`test_string_id_response_is_matched`、`test_undecodable_stdout_fails_fast_not_30s`（断言 `client.dead is True`）、`test_dead_server_marked_in_health` |
| M5-3 CLI 配置的 MCP 工具出现在 `/tools` | ✅（间接） | `test_build_registry_lists_mcp_tools`；`/tools` 本身由 `test_http_surface` 一路覆盖 |
| M5-4 坏 `mcp.json` 走结构化 McpError 而非 500 | ✅（服务层） | `test_manager_negative_cache_does_not_respawn` + `test_failure_paths_return_structured_error_codes`；`/api/mcp` 此前在任何 Python 测试里连路径字符串都没出现，现已由 M4-3 的清单门与 `test_http_surface` 的 mcp 契约测试覆盖 |
| M6-3 `bash start /m &` 被拒 | ✅ | `test_background_shell.py:121` `detached_command_reason("start /min notepad &") is not None` |
| M6-1/2/5 委托、软预算、写档默认只读 | ✅（测试层） | `test_subagent_delegation.py`(16) + `test_subagent_streaming.py`(5) + `test_parallel_writes.py` + `test_permissions_approval.py` 等合计 **91 passed**；写档需显式授权由 `WRITABLE_PERMISSION_MODES` 结构断言钉住 |
| M7-3 审批 60s 超时自动 deny | ✅ | 生产常量 `web.py:156 APPROVAL_TIMEOUT_SECONDS = 60.0`，测试 `test_approval_timeout_auto_denies` 用 5s 走同一分支并断言 `decision == "deny"` 且 `timed_out is True`（不为此把测试拖到 60s） |
| M7-1/2/4/5 hooks、slash、项目配置、composer 恢复 | ✅（测试层 + 前端真跑） | `test_hooks/test_slash_commands/test_project_config/test_mentions` 全绿；起 fake-provider 服务后 `node tests/frontend_{transport,lifecycle,scale,optimization}_smoke.mjs` **逐个 exit 0**（composer 恢复与取消在 transport/lifecycle 内） |
| M6-4 30 个 fixture 性能 P95 不超 M4 基线 15% | ✅ **已按 24 条全量结案（2026-09-25）** | 套件实际为 24 条（v2 定义即 24，路线图写作 30 是老口径）。干净全量零 429 死亡（M8-T16 退避修复生效）：p50 **50.2s** / p95 **~107s** / 最大 186.9s，全部落在 M4 基线（115s/826s）的 +15% 线内，性能标准通过。pass@1 **13/24 = 0.5417**、grading_coverage 1.0、false_completion_rate 0；总 tokens 2 097 337。**失败分解（11 条）**：完成守卫循环判死但隐藏 grader 实际通过 ×8、其他守卫判死但 grader 通过 ×2（version-exact 恢复证据、fix-uppercase 未验证）、真编码失败仅 ×1（multi-config）。交付正确率按 grader 单独算是 23/24。主导失败模式不是编码能力而是「评审要求运行测试 → 工作区无可运行检查 → 循环到上限」的不可满足循环，已作为新候选登记（见 2026-09-25 节）：评审可满足性注入与 M8-T19 重复判定提前停止。数据：`output/m6_4_full.results.json`（gitignored，报告在 `output/m6_4_full.{json,md}`） |

附带发现（对 M8-T14 的判断有用）：MCP 侧**已经**做对了这件事——`test_close_reaps_child_process` 明确钉住「关闭时回收子进程」。
也就是说「子进程必须被 reap」在本仓库不是新概念，只有 task worker 的 `Popen` 没走这条路（`task_manager.py:1824-1826`
`_closing` 时抛 `WorkerDetached` 且不 terminate、不留引用）。这把 M8-T14 的选项 A/B 之争收窄成
「宿主关闭时是否允许中止正在跑的 worker」，而不是「要不要 reap」。
### M4-7 / M8-T14 结案 + 一次「测试红了，但不是代码的错」排查（第四批，2026-09-22）

`pytest -q -W error` 从 **6 failed / 7 errors** 收到 **0 failed / 0 errors**。四条结论，按价值排序：

| # | 结论 | 证据 |
| --- | --- | --- |
| 1 | **M4-7 的 `-W error` 两条 ResourceWarning 已修；M8-T14 按选项 A 结案** | `TaskManager` 持有 worker 的 Popen 注册表，任何退出路径都必须处置句柄（`_retire_worker_process` 是唯一入口）：任务正常结束即 `wait()` 回收；宿主**干净关闭**（`_closing`）时先写 cancel 标志让 worker 自己收尾、有界等待 `WORKER_SHUTDOWN_GRACE_SECONDS=5s` 后 `terminate()`，再由 `_finalize_aborted_snapshot` 用租约围栏把记录写成 `cancelled` 并释放租约（否则下次启动会把一条用户已经停掉的任务当活任务接管）；**崩溃**脱管路径不杀（SQLite 里的 lease 才是监工），只把句柄交给后台 reaper 并按 CPython 的 `_child_created` 逃生口有意释放。先红后绿：把 `_retire_worker_process` 短路成「一律不杀」时 `test_clean_shutdown_aborts_a_worker_that_ignores_cancellation` 报 `worker kept running after shutdown`（心跳文件 108→210 字节）、`test_shutdown_abort_path_terminates_a_worker_it_cannot_cancel` 报 `shutdown left the worker running`；恢复实现后两条转绿，`pytest -q -W error` 全量 **904 passed** |
| 2 | **另外 5 条失败根本不是代码缺陷，是本机环境**：测试自撰的验证命令写死了 `python -m pytest`，而本机 PATH 上的 `python` 不是跑测试的那个解释器、没装 pytest → agent 的验证步骤 exit 1 → 进入 repair → `最大模型轮次已用尽` | 独立复现：`tool [exit 1]` 紧跟 `verification_required_before_finish` → `budget_exceeded`。修法是把测试与「环境里哪个 python」解耦（`conftest.suite_python()` / `suite_python_bin` fixture 用 `sys.executable`），CI 与已激活 venv 恰好都掩盖了这一点，所以它值得钉住 |
| 3 | **bench fixture 的第二根因也是环境**：本机全局 `core.hooksPath` 指向真实钩子目录，一次 `git commit` 耗时 **20.8s** > 15s 超时 → 每个 fixture 任务 `TimeoutExpired` | fixture 基线提交是内部记账，不该跑用户钩子：改为 `-c core.hooksPath=` + `--no-verify`，超时放宽到 60s（实测 2.3s） |
| 4 | **顺带修掉一个真实产品缺陷**：`run_bash` 主线程在读取线程仍 parked 时调用 `BufferedReader.close()`，Windows 上 close 会等这次读完成 —— 命令把输出管道交给孙进程后，工具调用要等满孙进程生命周期 | 实测：shell 在 3.7s 退出，`run_bash` 却 22.4s 才返回（孙进程睡 20s）、孙进程睡 45s 则等 45s。修法：读取线程关闭自己的管道，主线程只关闭读取已结束的管道。修复后 22.44s → **2.86s**，父进程输出仍被捕获 |
| 5 | **选了 A 之后，「宿主重启后 worker 继续存活」这条既有契约被重新定义**：继续存活的是**崩溃**后的 worker，不再是干净关闭后的 worker | 原测试 test_worker_survives_host_restart_and_continues_long_stream 用 `first.shutdown()` 模拟重启，正好踩在 A 要改掉的那条语义上。改成**真崩溃**（`test_worker_survives_host_crash_and_continues_long_stream`）：宿主跑在子进程里、被 `kill()` 直接打死，不跑任何清理，于是 worker 心跳文件继续增长、记录仍是 `running`、cancel 标志不存在，替换宿主按同一 lease owner/worker_pid 接管并跑到 `completed`，模型调用次数仍恰好 2 次（证明没被重新 spawn）。**教训**：只有真子进程崩溃才叫崩溃模拟——在测试里把 `shutdown()` 短路成 no-op 只是「假装没有清理」，它会连同 `_closing` 分支一起被跳过，什么也证明不了 |

**M4-3 的两个「标准不成立」项，处理方式不是改标准**：

- **rpc ≥10 method**：把只读协议面补全（`workspace/read`、`models/list`、`changes/read`、`sessions/list`、`permissions/read`），与既有 5 个生命周期 method 合计 **10 个**，每个一条测试，并复用同一套 `workspace_roots` 越界校验。
- **POST `/api/*` 的 Python 覆盖**：为审计点名「连路径字符串都没出现」的 6 个路由（`approval`、`changes`、`mcp`、`models`、`permissions`、`sessions/fork`）补契约测试（成功路径 + 校验失败 + 越界拒绝）。

**仍然未达成的部分（不掩盖）**：M6-4 的 30-fixture 性能基线依旧没有可信分位数——第五批跑到了 8 条并给出分组区间，但 n=8 算不出 p95，且本机配额（10 RPM）下 30 条要付出可观的等待。M4-3 的「POST `/api/*` 覆盖率」**已于 2026-09-23 从「算不出来」转为实测通过**（`coverage[toml]` 进 dev extra，分派点 GET 20/20、POST 14/14，模块行覆盖 74.5% 单独报；见上方 M4-3 行的第三格）。**2026-09-24 追记（M8-T35）**：那个分派点数当时的量法是「比较行执行过没有」，一次走到链尾的请求就能把它喂满（实测 `POST /api/nope` 一条 = A 14/14 而 B 0/14）；量法已改为**分支体进入覆盖**并落进仓库（`scripts/route_coverage.py --check`），换口径后 GET 20/20、POST 14/14 依旧成立。

**一条过程教训（写给下一个跑套件的人）**：这两次全量跑都与我并发编辑源码重叠，而 `tests/test_packaging.py` 的 module 级 fixture 会在构建期读取整个源码树 —— 边改边跑时它报的 `AssertionError` 可能是「构建快照撞上正在写入的文件」，不是打包缺陷。判定打包是否真的坏了，必须在不改任何文件的窗口里重跑。

### M6-4 真跑：8 条样本、一个配额事实、一个真实缺陷（第五批，2026-09-23）

用户选择「先跑小样本给区间」，所以这一批的目标不是补基线，而是**把能测到的测准、并如实标注测不准的部分**。三条结论：

| # | 结论 | 证据 |
| --- | --- | --- |
| 1 | **本机网关是 stepfun `step-3.7-flash`，配额 10 RPM**，而 8 条串行任务里 4 条死于 `request limited RPM reached, current: 11, limit: 10` | `output/m6_4_sample.results.json` 逐行 `error` 字段。runner 本身**没有并发**（`minicc/behavior_bench.py` 里 grep 不到 `concurrency/ThreadPool/max_workers`），也就是说**单个任务自己的多轮请求就能打满一分钟 10 次**——不是"跑太快"，是配额太小 |
| 2 | **429 是可重试错误，但预算比窗口短 → 由配额直接判死任务**（修完即 M8-T16） | 探测脚本（假 `MockTransport` 网关，零配额消耗）：限流器在 3s/15s 后解除时任务恢复；在 **60s** 后解除时 `ok=false, elapsed=15.06s, http_attempts=5`，错误串与 bench 现场逐字相同。修后同一探测 `elapsed=105.05s, attempts=4, ok=true`。代价也量出来了：**解除得快的限流现在多等 15s**（`window=3` 从 3.03s 变 15.02s），因为无法凭一次 429 区分窗口长度——用一次保守等待换整条任务不被判死 |
| 3 | **8 条样本给的是区间，不是分位数**；写进标准必须分组 | 干净 4 条：5.2 / 34.3 / 41.3 / 110.2s，通过 3/4，tokens 中位 31 475。429 污染 4 条：22.2 / 22.3 / 51.8 / 60.9s，通过 **0/4**。把污染组合进去算 p95 会得到一个既不代表能力、也不代表性能的数字 → 第三节 M6-4 行改为 🟡，并明确「P95 ≤ 基线 +15%」这条**仍未验证** |

另外记一笔方法论：这批的失败样本里只有 `v2-license-mit` 是真实能力信号（M8-T17，未结案）。判据是**错误串是否来自配额/环境**——来自 429 的四条不进能力账，122k tokens 的连续四轮"要求继续"才进。

### M1-3 复核：一条写着「人工核查」的标准其实在 wire 上可执行，而且当场不成立（第六批，2026-09-23）

M1-3 是唯一还挂着「未复核」的行。逐行读两条协议分支 + 一条 wire 级测试，产出三条结论：

| # | 结论 | 证据 |
| --- | --- | --- |
| 1 | **「假网关只发 delta + `[DONE]`、不发 finish_reason」根本不需要人工核查**，它有确定的可执行判据 | 新测试用 `httpx.MockTransport` 返回真 SSE 字节（一条 content delta + `data: [DONE]`），断言真实 HTTP 计数 == 1、`run_agent` 以明确 error 结束、已流出的文本保留在 answer 里。全绿 |
| 2 | **旧测试的「只发 1 次请求」数的不是 HTTP 请求** | `test_m1t5_stream_without_finish_reason_fails_fast` 把 `provider._create` 整个换成假函数，`calls["n"]` 计的是**我们这一层**被调了几次。它证明「没有重放」，但不证明网关只收到一次——附录 D 那句括号因此被改写成口径修正，而不是当缺陷修 |
| 3 | **「空答案不算成功」当场不成立**：一轮既无内容又无工具调用的完成会被当成功交付 | `loop.py` 两个交付点写 `result.answer = text or "(模型返回空回复)"` 而 `result.error` 留空；全仓库 grep 那个占位串**只命中 loop.py 自己**——从来没有测试引用过它。新断言先红（`assert None` 于 `TurnResult(answer='(模型返回空回复)')`），两处改成显式 `empty_answer` 失败后转绿，全量 `-W error` **913 passed** |

**这批最值得留下的一条方法论**：写着「人工核查」的验收项，先问一句「它能不能表达成一次函数调用」。M1-3 三条子里两条能（第 1、3 条），而且第 3 条正是靠"能"才被发现的——一旦要去写那个断言，就不得不去找"成功"在代码里的确切定义，然后发现它对空答案根本没有定义。

### M8-T17 判据就位：失败的任务从来没被客观判据看过一眼（第七批，2026-09-23）

先确认它不是偶发：同一 fixture 独立重跑第二次 **16 轮 / 127 487 tokens / 134.5s**（第一次 15 / 122 345 / 110.2s），
错误串一字不差（`完成评估连续 4 轮要求继续但未收敛`），证据落在 `output/m8_t17_repro.results.json`。

但重跑没有回答那个真正要回答的问题，因为评测器有一条结构性盲区：

| # | 结论 | 证据 |
| --- | --- | --- |
| 1 | **被评委封顶的任务永远不会走到客观评分**：`benchmarks.py:621` 的评分分支前置条件是 `entry["status"] == "completed"`，非 completed 直接 `entry.update(passed=False, grader_type=...)` 了事 | 于是「评委假阴性（文件其实已经写对了）」和「真的没做完」在结果文件里长成同一个样子。M8-T17 上一版写的「先取评审事件序列再定改法」其实取不到——事件列表 `_chat_locked` 返回了（`web.py:2323`），但 runner 把它整份丢弃 |
| 2 | **`max_completion_continues` 是一个不可配置的旋钮**：`web.py:1434` 写 `getattr(self.config, "max_completion_continues", 3)`，而 `Config` 里根本没有这个字段 | `getattr` 的默认值 3 因此永远生效，`max(1, int(...))` 也永远不可能被用户改到。与 M8-T16 那类「文档声称可配、代码里读不到」同类，但这次是**读取端伪装成可配** |
| 3 | 判据补齐：`review_rounds` + `objective_oracle` 两个诊断字段 | 前者把每轮 `completion_judge` 事件的 `code/status/rationale/missing/next_action` 收成有界尾巴（留 8 轮、每条文本截 200 字符、`missing` 留 6 项），只在非 completed 时写；后者在同一个前提下**照跑一次确定性 grader**，把结果塞进 `objective_oracle`，`passed` 与 `false_completion_rate` 一律不动。竞态守卫：`worker.is_alive()`（超时后被抛弃的线程还在写工作区）时直接不看，返回 `None` |

**红→绿证伪**：把 `minicc.benchmarks._objective_oracle` 桩成返回 `None`，参数化的两条断言立刻
`KeyError: 'objective_oracle'`（`reviewer-false-negative` 与 `genuinely-incomplete` 双红）；接回真实现后
`tests/test_benchmark_runner.py` 16 → 19 passed。全量 `pytest -q -W error` **917 passed in 271.56s**（上一基线 913）。

**这批的方法论收获**：一条「待查的能力失败」如果落在只看结果的评测器里，真正缺的往往不是更多样本，而是
把已被丢弃的中间证据接出来。下一批用一次真跑读这两个字段，再决定 M8-T17 的改法（候选：`missing` 集合
连续重复即判停的失速检测、把 `max_completion_continues` 真做成配置项、以及是否让封顶任务也进入正式评分——
最后这条会改 `passed` 语义，不在本批范围内）。

判据接出来之后，同一批就把 M8-T17 结掉了，结论比原候选三条都更靠前：**那句要求根本不是模型给的。**

真跑读数（`output/m8_t17_oracle.results.json`，`runtime_source_sha256 c4ec2331`）只有两行有意义：

```
review_rounds: 4 × {"code": "completion_continue",
                    "missing": ["为最近的代码修改运行相关测试或检查，记录结果后再验收"],
                    "rationale": "已修改文件，但没有修改后的客观检查记录。"} + 1 × completion_continue_capped
objective_oracle: {"passed": true, "case_count": 2, "exit_code": 0}
```

| # | 结论 | 证据 |
| --- | --- | --- |
| 1 | **交付物本来就是对的**：文件契约两条 `contains` 全过，`passed:false` 完全来自「没走到评分」这一步 | 于是这条一直记作「能力失败」的样本真实身份是**评审链路的假阴性**。只跑一次、只看 `passed` 列的话，这个结论永远拿不到 |
| 2 | 四轮一字不差的 `missing` 来自 `agent/completion.py:415-419` 的**确定性后置门**，不来自模型 | 规则：最后一个成功写事件之后必须出现客观检查事件。`is_documentation()` 只认 `.md/.rst/.txt/.adoc`，而 `LICENSE` **没有后缀** → `needs_execution=True` → 唯一能满足它的是 `is_verification_evidence` 认可的真检查器（`tool_policy.py:142-150`：pytest/mypy/tsc/ruff check/npm test…）。该 fixture 只有一个 README 和一个 LICENSE，没有任何可跑的东西；即便去跑 `pytest`，非 0 退出码会让事件 `status != "ok"`，同样不清门。**这条要求在它触发的场景里按构造不可满足** |
| 3 | 修法只有一句：把「无后缀的法律/说明类文本」归回文档 | `suffixless_prose = {license, licence, copying, notice, authors, contributors, acknowledgements, patents}` 命中即走本来就客观的「读回来看」支路（`read_file`/`git_diff`）。**没有放松「改代码要跑检查器」**：`Makefile`/`Dockerfile` 这类无后缀构建文件仍然必须跑真检查器，由 `test_extensionless_build_file_still_demands_a_real_checker` 钉住 |

**同一 fixture、同一网关、同一条命令的真跑复核**：

| 运行 | 源码哈希 | 轮次 | tokens | 延迟 | 结果 |
| --- | --- | --- | --- | --- | --- |
| `m8_t17_repro`（修复前） | `237ad7a2` | 16 | 127 487 | 134.5s | failed / passed False |
| `m8_t17_oracle`（修复前 + 判据） | `c4ec2331` | 15 | 125 518 | 151.3s | failed / passed False，**oracle True** |
| `m8_t17_after_fix`（修复后） | `10381ccc` | **6** | **33 078** | **31.2s** | **completed / passed True** |

约 3.8 倍 token 差、2.4 倍轮次差，而且第三行是「走完正常验收路径通过」，不是靠封顶侥幸。一条口径提醒：
三行的 `code_revision` 有两行同为 `71328f3`（HEAD 的提交号），**工作区里未提交的改动不会改变它**，
能区分代码版本的只有 `runtime_source_sha256`——引用 bench 证据要引后者。

**本批方法论**：一个「看起来像模型能力上限」的失败，先问它的判据**能不能被满足**。确定性后置门 + 有界重试
这个组合最容易产出这类失败：模型侧怎么看都在原地打转，代码侧其实只是在一遍遍执行一条永远为真的规则。
判据接出来以后，答案在 5 行 JSON 里就写完了。原候选里的失速检测因此**降级为待观察**（记入 M8-T19），
而「`max_completion_continues` 不可配置」那条被追成了一整类缺陷，见下一段与 M8-T18 行。

**为什么不当场做失速检测**：最直觉的版本是「`missing` 连续相同就提前停」，但两次相同就停会误杀
「agent 第一轮没听懂、第二轮才去做」的正常收敛；要做就得带上活动信号（要求相同**且**本轮没有新增检查类工具调用）。
本批已经消灭了不可满足的要求，这条改法失去了触发样本，凭 1 个 fixture 去改收敛判据正是这份文档一路在避免的事。

本批最终基线：`pytest -q -W error` **919 passed in 215.55s**（判据两条 + 门修复两条，913 → 917 → 919）。

### M8-T18：一条「旋钮拧不动」的报告，先变成门再修，门第一次运行就报出三个（第八批，2026-09-23）

M8-T17 结案时顺带记下一条：`max_completion_continues` 被 `getattr(self.config, ..., 3)` 读取，而 `Config`
没有这个字段。如果当时直接给这一处补字段，它就只是第 884 个补丁。先问「这类缺陷能不能表达成一次函数调用」，
答案是可以，而且代价极低：AST 扫 `minicc/**/*.py`，凡「target 末段是 `config` 的三参数 `getattr(obj, "字面量", 默认)`」
都要求那个字面量出现在 `dataclasses.fields(Config)` 里，另加 `_MIN_SITES = 30` 防空清单假绿
（见 `tests/test_config_surface.py`，也见「第二批」里 M4-3 那条同类先例）。

**门第一次运行报出三个死旋钮**，其中一个是我原本没在看的：

| 键 | 读处 | 后果 |
| --- | --- | --- |
| `max_completion_continues` | `web.py:1434` | 完成评估的续跑上限一直恒为 3，用户/项目层/环境变量三层都拧不动 |
| `anthropic_base_url` | `main.py:618`、`web.py:1390` | 两处都写 `or self.config.base_url` → Anthropic 协议永远只能跟 OpenAI 用同一个端点，自建/代理网关配不出来 |
| `task_worker_runtime` | `task_manager.py:1011` | 全仓库仅此一处引用，没有任何实现语义 → `not getattr(..., False)` 恒真，条件形同注释 |

三种后果对应三种不同修法，这一点比"三个都补字段"重要：前两个**声明成真字段并接上 env + 项目层键**
（上限夹在 1..8，未设的 `anthropic_base_url` 仍回退 `base_url`，行为不变）；第三个**删掉幽灵条件**——
给它补一个字段等于新造一个没人实现的开关，而删除后的运行行为与今天逐字节相同。

`tests/test_project_config.py` 16 → 20 覆盖可达性与夹取（`0/-4/99` → `1/1/8`、非整数抛 `ConfigError`）；
门的红→绿是拿 HEAD 版 `config.py` 桩回去量的，三条同时报红，接回即绿。全量基线见本批末尾。

**一次必须记下的偶发**：本批第一次全量是 `6 failed, 921 passed`，可见的两条都在 `tests/test_web_security.py`
（`test_open_loopback_auth_not_required`、`test_cross_origin_state_change_rejected_before_any_work`），
另 4 条名字被管道截断没取到；单独重跑该文件 **17 passed**，同一份工作区代码第二次全量 **927 passed in 297.41s**。
所以它**没有**被当成缺陷修，但也**没有**被当成不存在：这些测试绑固定端口，本机当时还留着一小时前 bench 真跑的资源，
在改完 config 数据类字段顺序的同一次运行里出现，光看结果无法排除因果。下次再见到同一批失败要先按
「同代码两次全量 + 单跑」定性和它划清界限，别直接把「偶发」写进结论。

**可迁移的一条**：`getattr(obj, "key", default)` 这种"防御式读取"在任何一个字段缺失时都会安静地返回默认值，
所以**它把配置缺陷伪装成了配置成功**。缺一个字段只会在很久以后表现为"用户说他设了但没生效"。
凡有这种写法，就该有一条门把字面量和真实字段清单对起来——这比修掉当次那一个更便宜。

### M8-T20：同一批自己踩到的第二半——旋钮拧得动，但没人查得到（第八批续，2026-09-23）

M8-T18 收尾时我准备直接提交，被一个反问拦住：这两个新旋钮**除了代码，还有哪里说它们存在**？
`minicc.config.example` 和 `README.md` 都逐条列举 `MINICC_*`，而我只写了 `config.py`。也就是说，
如果用户不知道一个键的名字，"可配置"和"不可配置"在他那一侧是同一个状态——**可达性有两半**。

把第二半也做成门（扫 `config.py` 里每个 `"MINICC_*"` 字面量，要求同时出现在示例文件；另加读取面下限
`键数 >= 30`，防正则失效后对着空清单假绿），**第一次运行报出 17/37**——缺口不是我这两个键，而是整个
配置面长期没人对过账。清单里有 `MINICC_HOME`、`MINICC_SANDBOX` / `_IMAGE`、`MINICC_TASK_EXECUTOR`、
`MINICC_MAX_CONCURRENT_TASKS`、`MINICC_CONTEXT_WINDOW_TOKENS` / `MINICC_COMPACT_THRESHOLD`、
`MINICC_SOFT_MAX_TOKENS` / `_DURATION_SECONDS`、`MINICC_SUBAGENT_WRITABLE` / `_MAX_DEPTH` / `_MAX_TOKENS`、
`MINICC_FALLBACK_MODELS`、`MINICC_AUTO_RESUME_ON_START`、`MINICC_TASK_HISTORY_LIMIT` / `_MAX_AGE_DAYS`、
`MINICC_ALLOW_PRIVATE_MCP`，全是有真实语义的用户开关。

补文档的过程本身就是复核，而且**纠正了三次凭印象的写法**：① `MINICC_HOME` 不要求目录已存在
（`home_dir` 只在"指向已存在的非目录"时报 `ConfigError`，缺失由写入方创建）；② `_optional_positive_*`
系列里"留空 / 0 / off / unlimited / 非正数"一律表示**不设**，只有非数字才报错——写成"必须正数"是错的；
③ `soft_max_*` 只经 `Budget.soft_limit_hit()` 提示模型收尾，**永不中止任务**（和示例文件里那句"没有总时长
上限"一致），而历史保留的 `prune()` 只删已终结快照、排队与运行中的记录永不清理。三条都是读实现才写得出的。

**门的作用域刻意停在 `config.py`**：全包扫还有 7 个开发者开关（`MINICC_FAKE_PROVIDER`、
`MINICC_FAKE_PROVIDER_FAULTS`、`MINICC_EVAL_GRADER_DIR`、`MINICC_HOOKS`、`MINICC_KEEP_WORKER_CONFIG`、
`MINICC_PRICING_JSON`、`MINICC_ANTHROPIC_MAX_TOKENS`）不该出现在用户示例文件里，扩大作用域只会逼文档掺进
内部实现细节，或者反过来把内部开关伪装成用户接口。

**双向红→绿都量过**（这条门的两个失败方向不对称，只测一个会漏掉一半）：从示例文件删掉那两个新键 →
报 `MINICC_ANTHROPIC_BASE_URL；MINICC_MAX_COMPLETION_CONTINUES`；反过来给一个尚未文档化的键补文档 →
当时那个"清单只缩不涨"的版本立刻报 `请把它们从 _UNDOCUMENTED_KEYS 删掉：MINICC_HOME`。
文档补齐之后清单可空，实现因此收成一个不带例外的断言；保留的那条测试改测扫描下限。
`tests/test_config_surface.py` 4 条 + `tests/test_project_config.py` 20 条 **22 passed（-W error）**。

**同一把尺子顺手量过 CLI，结论是「没有缺陷」，也一并记下免得重复查**：`_apply_cli_overrides` 写进 `updates`
的 12 个键全部是 `dataclasses.fields(Config)` 的成员，桥是 `replace(config, **updates)`（不是
`load_config(**updates)`——后者只接 7 个显式参数，会把这 12 个键全炸掉，这条路径本来就是对的）；
`--sandbox` / `--provider-type` / `--task-executor` 靠 argparse `choices` 挡住非法值，
`--max-concurrent-tasks` 另有一条与 resolver 同界的显式检查；`config.max_turns` 确实被
`main.py:387`、`web.py:1155/1945` 读走，不是"设了就忘"的死旋钮。**"没有缺陷"不等于"没查"**——
这一圈的价值在于把 CLI 这条第二路径从待查清单里划掉。

### M8-T21：同一把尺子的第三格——字段挂着，但没有任何一层会写它（第八批续，2026-09-23）

前两格量的是「读处有没有这个字段」和「文档有没有提到这个键」，这一格反过来量 **字段有没有人写**：
`Config(...)` 构造的关键字集合必须覆盖 `dataclasses.fields(Config)`（同样带 `>= 30` 下限，防扫不到构造时
对着空集合假绿）。**第一次运行就报出 `timeout`**：它是 `Config` 字段、被 5 处真实 HTTP 调用读走
（`main.py:619/627`、`web.py:1000/1170/1415`），但 `load_config` 从不解析它——仓库里既没有 `MINICC_TIMEOUT`，
`config.json` 也没有 `timeout` 键，唯一入口是交互 CLI 的 `--timeout`。按运行方式分组才看得出后果的不对称：
CLI 用户能改；**Web 工作台（`web.py:2489` 裸调 `load_config`）和它派生的每一个 task worker
（`task_worker.py:53` 同样裸调）永远锁在编译期的 180s**，而一次高推理强度的非流式请求完全可能超过它，
部署侧没有任何办法调整——这正是慢网关环境下最该能配的那一项。

修法沿用 M8-T18 的形状：`MINICC_TIMEOUT` env + `timeout` 文件键走同一个 `pick`（于是 `.env`、用户层、项目层
三层都可达），非数字与非正数抛 `ConfigError`，上界夹 3600s——`1e9` 这种笔误会把「超时保护」变成
「永久挂起」，和 `max_completion_continues` 一样按成本上限处理；`--timeout` 也收到同一上界，避免两条路口径不一。

**真机验证（不消耗任务配额，只发两次真实请求）**：`MINICC_TIMEOUT=1` 且 `MINICC_PROVIDER_RETRIES=0` 时，
构造出的 provider 客户端 `client.timeout` 逐字等于 `1.0`，真实请求 **3.80s 后 `APITimeoutError: Request timed
out.`**；同一提示词改 `MINICC_TIMEOUT=120` 则 3.34s 正常返回。也就是说这个值不只是进了 `Config`，
它真的止住了 socket。诚实记下边界：120s 那次返回的 `content` 是空串（400 max_tokens 全被推理消耗），
所以第二次只证明「客户端不再掐断请求」，不证明答案质量——后者是 137e76a 那条「无答案轮次不再当成功交付」
的职责，不在本条范围。

**这条门的边界必须写清**：它查的是「字段完全没进构造」，**不查**「进了构造但值是常量」。`max_turns` 属于
后者（`load_config` 里恒为 `None`，是刻意的 legacy 忽略，见 `config.py:331-338` 的注释，CLI 保留显式逃生口），
所以它和 `max_duration_seconds` / `max_tool_calls` 一起进 `_CONSTANT_FIELDS` 例外表。**豁免写成表而不是把门调松**，
是为了让「谁被豁免、为什么」可审——一条不会失败的门没有价值，一条看不出自己边界的门有害。


### M8-T22：三格尺子全是开发者视角，第四格要站在写配置的那个人那侧（第九批，2026-09-23）

触发点是上一批留下的未结案观察项：`MINICC_SANDBOX` 的裸键是 `sandbox`，字段却叫 `sandbox_mode`。回去
triage 时先把命名约定量化，而不是直接改这一处：AST 扫 `config.py` 的 34 个 `pick()` 调用点，**33 个满足
`MINICC_X ↔ 裸键 x ↔ Config 字段 x`，只有 1 个例外**。如果视线停在这个例外上，改法就是给一个键补个别名——
一行的价值。真正值钱的是顺手问的那句「用户还能怎么把它写坏」：任何拼错的键。而 `load_config` 对一个不存在
的键的输出是**零字节**，`config.py` 文档字符串里那句 *"nothing silently defaults when the user explicitly
set something"* 只对**坏值**成立（每个键都有 `ConfigError`），对**坏键名**从来没成立过。

还有一条来自同一处的证据：`sandbox` 这个拼法在全仓库只出现在 `tests/test_core.py:24` 的 fixture 里，而那条
测试断言了 `api_key` / `base_url` / `model` / `yolo`，**唯独没断言 `sandbox_mode`**。也就是说「这个键有测试覆盖」
的错觉，来源是一行没人读的 fixture 数据。已补断言。

**词表从哪里来，决定这条改法会不会腐烂。** 没有手写键名清单，而是让 `pick()` 记下自己真正查过的每个键名
（env 名 + 裸键 + 别名），解析完再回头比对两层 `config.json`。理由是 M8-T20 刚刚量过的：清单式的文档会漂
（17/37 个键没人写），而「解析器实际查过的键」就是定义本身，新增旋钮不需要记得登记。附带好处是一个反腐蚀
探针——某个键哪天不再被读取（改名或废弃），它会立刻出现在启动报告里，而不是安静地变成默认值。

**假绿防御用的是哨兵键**：参数化门对示例文件里每个旋钮都断言「报告出来的键**恰好等于**哨兵」，而不是
「报告为空」。「没报错」类断言是「不打印」类断言的镜像问题——报告器一旦坏掉，36 行门会同时变成永远满足。
红→绿量的就是这个：把 `_unrecognized_layer_keys` 短路成 `return []`，stray / retired / 项目层 / print-config
四条测试立刻红（另外三条按构造仍绿，它们防的是假阳性那一侧：两种拼法都要能用、`.env` 必须保持静默）。

**建议阈值是量出来的**：`difflib` 的 cutoff 取 0.62 时会输出「`MINICC_LOG_LEVEL` 是否想写 `MINICC_MODEL`？」——
用户照做只会更糟。判据写成一句可操作的话：**建议必须能让用户的下一步真的做错事变成对事，否则宁可不给**。
提到 0.78 后这类跨语义误配消失，`compact_threshhold → compact_threshold` 这种同词根误配保留。三个刻意废弃的
硬预算键（`max_turns` / `max_duration_seconds` / `max_tool_calls`）单独走「已废弃 + 替代键」文案，不参与猜测。

**三条边界都必须写在案上，否则后人会把它当噪音拆掉**：① `.env` 不做这项审计（它合法地装着 `PATH` 之类的
无关变量，报出来就是噪声工厂）；② 「只能走环境变量」的豁免清单要有一条反向门守着——停在清单里的键必须
**确实不经过 `config.py` 解析**，否则豁免表会变成藏污处；③ `MINICC_SANDBOX` 两种拼法都认，`sandbox` 优先。

其中②这条门上线第一次运行就把**我自己的扫描器**判红了：第一版用正则 `_config_env_keys()` 判断「有没有被
config.py 读取」，于是 `MINICC_HOME`（出现在 `os.getenv`）、`MINICC_ALLOW_PRIVATE_FETCH` / `_MCP`（出现在
M2-T8 的导出清单）被当成「已被解析」，豁免被驳回。换成按 AST 读 `pick()` / `_optional_positive_*()` 的
**字面量参数位置**才得到正确答案。这是本会话第二次撞到同一个错误：**字面 grep 不是读取语义**（第一次见
M4-3 的验收门）。以后凡是「某键/某路由有没有被处理」的判断，第一版就按调用点的参数位置扫，别按字符串扫。

**顺带一条独立的文档发现**：README **从来没有提到 `config.json` 存在**。M7-T4 的退出标准第 4 条写的是
「项目级覆盖生效**且优先级文档化**」，当时的证据是 `config.py` 的文档字符串——那是开发者文档；用户会打开的是
README。已补一节「配置文件层（`config.json`）」，含两层路径、完整优先级、键名两种写法、只走环境变量的六个
键，以及新的 `ignored_keys=` 报告。**判据**：标准里出现「文档化」时，要问「用户会打开的那个文件里有没有」。

真机核对（`.venv/Scripts/minicc.exe --print-config`，一份含 `max_truns` / `compact_threshhold` / `sandbox_mode`
的用户层文件）：stderr 两条 WARNING，后者带「是否想写 `'compact_threshold'`？」；`sandbox_mode` 不再被误报；
stdout 只有两行协议输出，末行为 `... ignored_keys=compact_threshhold,max_truns`——日志没有污染 stdout，
这条是 M8-T5「stdout 是协议通道」的既有契约，本次新增的输出必须继续满足它。

**真实模型复核（REPL 一条只读指令，非 `--print-config` 那条旁路）**：临时 `MINICC_HOME` 放一份
`{"max_truns": 3, "sandbox_mode": "host"}`，cwd 用仓库真实 `.env` 的阶跃网关 → 启动即 stderr 一条
`用户配置 ... 中的键 'max_truns' 不会被读取（已按默认值运行）`；会话本身正常交付（回答 `收到`，
`total_tokens=3658`），`sandbox_mode` 那一项不再被误报，stdout 全程只有 REPL 内容。两个入口（离线
`--print-config` 与真实一次运行）各自量过，才算这条标准落地——只量一个正是 M8-T9 记录过的老毛病。

本批最终基线：`pytest -q -W error` **982 passed**（938 → 982，+44 全部来自 `tests/test_config_surface.py`
6 → 43 与 `tests/test_project_config.py` 25 → 32）。同一批的 wall time 是 518.39s，而本仓库平时同规模是
260-310s：新增 44 条自己量出来只有 1.8s / 21.9s，差额不在我这边，运行期间机器上另有并存的 python 进程，
**归因未证实**，因此这个数字只用来记「这次跑了多久」，不进性能口径（见「第一批」的 M1-1 行）。


### M8-T23：`/api/metrics 与单任务快照对得上`——真跑一次就撞出四条（第十批，2026-09-23）

**起点**：M8 退出标准第 5 条最后一句。`web.py` 里 `metrics()` 的文档字符串写着 *"so `/api/metrics` can
never disagree with `GET /api/tasks/<id>`"*。按上一批立下的规矩，一句「不可能不同意」恰恰是最该被拿去
量的东西——所以这次不先读测试，直接起真进程量。

**量法**：真实 `AgentService` + fake provider，跑一个两子任务的并行批，把 `task_manager.list()` 的逐行、
父任务快照、`metrics()` 三者并排打出来。

**发现一（P0：文档里写着的批任务功能当场不可用）**：父任务 `status=failed`，error 逐字是
`批任务 watcher 失败: TypeError: AgentService.merge_batch() got an unexpected keyword argument 'model'`。
`task_manager.py:1679` 传 `model=parent.model`（每个任务携带用户选的模型），而 `AgentService.merge_batch`
从没接受这个参数——**凡是子任务全部成功的批，都在合并那一步死掉**，README 里还留着 `POST /api/tasks/batch`
的调用示例。982 条测试为什么全绿：两半边各自对着一个不像对方的替身测。批任务测试用的 fake service **根本没有
`merge_batch`**，`hasattr` 守卫于是整段跳过；`merge_batch` 自己的测试用 `AgentService.merge_batch(service, ...)`
**不绑定地**调一个 `SimpleNamespace` 假 self。签名修好后那条老测试反而红了——它必须换成真 `AgentService`，
而这正是它的替身一直替它掩盖的东西（红→绿方向反过来的一次巧合式证明）。

**发现二（同一处的口径错：批任务被记两次）**：批父任务快照本来就把子任务用量汇总进去（`_watch_batch` 里
children + merge 相加），而 `metrics()` 是把 `list()` 的每一行相加——父行与子行都算，同一批模型调用记两次。
离线量出的具体数字：修复前一次两子任务批 = 父 1315 tokens，逐行求和 2405（**+83%**）。修法取「每棵子树只在
根上记一次」：`metrics()` 只累加 `parent_id` 为空的行，被排除的行数放进 `subtask_rows`，不是偷偷丢掉。
方向相反的另一半同时暴露：自动编排那一支是**少记**——父任务接管后跑 `_run`，`apply_result` 用本次运行的
usage **整份替换** `tokens_used`，侦察子任务的 token 只留在子行里。于是新增 `_roll_up_children()`，让
「父任务快照 == 整棵子树」这个不变量在两条路径上都成立，`metrics()` 的排除规则才是对的（否则同一把尺子
在批任务上多算、在自动编排上少算）。

**发现三（一条恒真断言）**：`tests/test_logging.py::test_metrics_endpoint_reconciles_with_task_snapshots`
里 `payload["cost_usd"] == approx(per_task_cost)` 两边都是 `0.0`：fixture 用 `test-model`，
`pricing.cost_usd()` 对未知模型返回 `None`，而它自己写的 `priced + unpriced == 2` 把「全部未计价」也算通过。
补 `MINICC_PRICING_JSON` 给 test-model 定价后，成本这半边第一次在比一个非零数；断言同时收紧成
`priced_tasks == 2 / unpriced_tasks == 0` 并加 `cost_usd > 0`。

**发现四（一个跨工作区的总数挂着单工作区的名字）**：不带 `?workspace=` 时 `metrics()` 累加的是共享任务索引
里**所有**工作区的行（`TaskManager.list(None)` 根本不过滤），响应却把 `workspace_path` 填成服务自己的目录。
改为 `workspace_path: null` + 新增 `scope`（`all_workspaces` 或回显过滤路径），README 同步。

**真跑方法本身的一条坑（假归因）**：探针第一趟选 8791 端口，`/api/health` 返回 200 就当作「我的服务器起来了」。
实际上 8791 早有别的进程在听（`netstat` 查到 PID 33676），我 spawn 的那个因端口占用直接退出，于是那趟 POST
打到的是**别人正在跑的旧代码进程**——报出来的 TypeError 与我的修复无关。第二趟加了两道闸：先 bind 一次端口
证明它空着；起服务后做「应答者身份」探测（`/api/metrics` 里是否已有新字段 `subtask_rows`）再决定是否提交任务。
真实网关复跑（阶跃 `step-3.7-flash`，两子任务）：批父任务 `completed`、rolled-up `total_tokens=50323`、
`cost_usd=null`（该模型未计价，诚实返回 null 而不是 0），合并答复是真读出来的（README 首行
`# minicc-codex`、`docs/ROADMAP_TO_PRODUCT.md`、`docs/GAP_ANALYSIS_AND_ROADMAP.md`）而不是编的；
`/api/metrics` 报 `task_count=23 / subtask_rows=4 / usage.total_tokens=50323`，与只读 SQLite 复核逐字节相符
（该工作区只有这一个根任务带用量，naive 逐行求和会到 99688）。

**门与实现**：
- 新增 `tests/test_batch_wiring.py`（5 条）。核心那条用 AST 扫 `task_manager.py` 里每个
  `self.service.X(...)`，拿 `inspect.signature` 对**真实** `AgentService` 方法做 bind；红→绿判据逐字：
  `task_manager.py:1679 calls self.service.merge_batch(on_stream, on_usage, reasoning_effort, model,
  workspace_path, cancel_event): got an unexpected keyword argument 'model'`。带 `_MIN_CALL_SITES = 2`
  与「`merge_batch`/`_run_chat` 两个接缝名必须在扫描范围内」防空清单假绿；`**kwargs` 动态调用（`_run_chat`
  那处自己就用 `inspect.signature` 探测）显式跳过并写明原因。这条门查的是**这一类**缺陷（接缝两侧各自正确），
  而不是只有这一个参数。
- 把 `merge_batch` 里第三份手写的 provider 构造抽成 `AgentService._make_provider()`：`_run_chat` 的闭包与
  合并器现在在同一处映射 config → client。之前合并器既不认 `MINICC_FAKE_PROVIDER`（所以这一段在 CI 里
  根本无法端到端跑）、也不认 `provider_type=anthropic`（Anthropic 网关下的批任务会用 OpenAI 线格式发合并请求）。
- 另外三条真跑门：批任务经真实 `AgentService` 走完并 `completed`；`merge_batch` 的 `model` 与 `provider_type`
  落到 provider 构造参数；`metrics` 对批任务只记一次（含 `task_count=1 / subtask_rows=2` 的可见性）。

**边界（这条没覆盖什么）**：`_roll_up_children()` 只在父任务正常收尾时汇总；父任务被取消/崩溃时子任务用量
仍只留在子行里，此时 `metrics()` 因为排除子行会少记——这条按已知边界保留，因为「取消的批到底花了多少」需要
先定「被丢弃的一次性任务要不要计入用户可见成本」这个口径，不该在修 TypeError 的同一次改动里顺手替用户决定。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **987 passed**（982 + 5 条新门），exit 0。


### M8-T24：一条边界不修就是「只在成功时算账」——把汇总抽成一个收敛点，再逐条删掉它数有几条门变红（第十一批，2026-09-23）

**起点**：M8-T23 自己写下的那句边界。上一批把汇总抽成了 `_roll_up_children(task, result)`，但只在**父任务正常
收尾**时调用，并在文档里诚实地记了「取消/崩溃时子任务用量仍只留在子行里」。这一批要做的就是那句话：把它从
「一条已知边界」变成「一条不成立的命题」。做法不是先写新功能，而是先问「有几条路会走到终态」，再逐条删掉汇总
调用数红条数——**门的强度用删代码量出来，不用自述**。

**四条终态路径**（`_watch_batch` 三条 + `_run` 一条）：合并成功、有子任务失败（父任务 `error`）、合并期间被取消、
自动编排的父任务交回 `_run` 后崩溃。旧的 `_roll_up_children` 把数**塞进结果负载**，于是它天然只能覆盖前一条半：

1. **汇总必须发生在 `apply_result` 之后，而不是作为它的输入**。被取消的父任务在 `apply_result` 第一行就撞
   终态门槛（`if self.status in TERMINAL_TASK_STATUSES: return False`）——负载整体被拒，藏在负载里的汇总跟着
   一起被丢；藏在 `result` 里的汇总还依赖 `result` 存在，而 watcher 抛错那条路连 `result` 都没有。抽成
   `_roll_up_tokens(task)` 之后它只依赖记录本身，四条路共用一处。
   **实测（fake provider，两子任务）**：合并器抛错时父任务 `tokens_used == {}`，子任务真花掉的 **1090** tokens
   从 `/api/metrics` 里凭空消失——`metrics()` 按根计费、排除子行，而根上没有数。
2. **`snapshot()` 的末尾会用结果负载覆写记录字段**（`output.update(result_payload)`）。这条是读代码时发现的
   嫌疑，量出来是真的：只更新记录字段时，同一批同一时刻**用户看快照是 225、聚合看索引是 1315**（5.8 倍）。
   同一个坑在这个文件里已经有解药——`snapshot()` 后面就写着「结果负载不许覆盖主机维护的生命周期字段」，
   于是把 `tokens_used` / `cost_usd` 一起纳入那个保护块，并在汇总时同步 `result["tokens_used"]`，让落盘的
   行本身也带正确的数（重启后 `from_snapshot` 读的就是它）。
3. **新字段必须能往返**。`children_rolled_up` 进 `snapshot()` 也进 `from_snapshot()`；少进后者，重启恢复的
   父任务下一次收尾会**再汇总一次**——实测 `1315 → 2405`。幂等门槛（`folded` 早退 + 持锁二次检查）挡住的是
   「同一个父任务被收尾多次」这件事，而它真的会发生：watcher 交接、重试、后面还有 force-persist。
4. **顺带撞出来的独立缺陷（比前三条更像产品 bug）**：自动编排那条测试第一次跑就红在 `assert spent > 0`，
   因为子任务的 `tokens_used` 是 0——`TaskResult.to_payload()` **永远**输出 `tokens_used` 这个键，生产者没填时
   它是 `{}`，而 `apply_result` 把「键存在」当成权威，于是把这次运行逐轮上报过的 500 tokens 清成 0。
   判据换成**空负载 = 没有信息**（和 `cache_summary` 里已经写明的「missing ≠ 0」同一条原则）：非零负载仍然
   权威（包括它声明的归零结论由 fresh 记录自己覆盖），零/空负载不再抹掉已上报的量。

**门的强度（逐字红→绿）**：删 except 路径的汇总 → `assert 0 == 1090`；删幂等门槛 → `1315 → 3495`（两次额外
汇总各 1090）；删 `result` 同步 → 五视图分裂成
`{"snapshot": 225, "summary": 1315, "metrics": 1315, "persisted": 225, "persisted_result": 225}`；
删 `from_snapshot` 那行 → `assert 2405 == 1315`；删 watcher 成功路径的汇总 → **5 条同时红**。

**测试自己撞出的两个坑（值得单独记，因为它们会让断言为错误的理由通过/失败）**：
① `_wait()` 以「状态进入终态」为返回条件，可取消是**从 watcher 外面**把状态变终态的，汇总要等合并器返回之后
才发生 → 首读拿到 `{}`。空载下不复现、全量负载下必现，补 `_wait_billed`。
② SQLite 行是 write-behind 镜像，最后一次强制落盘排在状态变更之后 → 落盘视图必须轮询镜像追上再比（`_wait_row`），
一次性读取在全量负载下失败过一次（`persisted: 0`）。这两条都不是产品缺陷，而是**「等哪个信号」这件事本身需要被测
试写清楚**；判据没变（仍然是求和相等），变的只是别在中间状态取值。

**边界（这条没覆盖什么）**：被取消那一次里**合并器自己**花的 100 tokens 不归属——终态门槛拒绝的是整个负载，
要接住它得改「已终态任务能否接收迟到结果」这条状态机语义，比记账严重，不该顺路改；测试把这件事写成断言
（父任务 == 子任务之和，不含那 100）而不是留成口头说明。另外 `WorkerDetached` / `_reconnect_worker` 那条支路
不汇总：进程执行器下 worker 自己写镜像，父任务由镜像恢复，两处都汇总就会双计。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **994 passed**（987 + 6 条批任务终态门 + 1 条负载用量门），exit 0。

**真机复核（阶跃网关，真实模型，一条只读两子任务批）**：汇总第一次带着**真实 cache 计数**跑通——两个子任务
`9178 + 7186 = 16364`，父任务 `total_tokens=16884`（差额 520 = 父 − 子之和；把它归给「合并器自己那一次调用」是
**算术推断**，真机这一趟没有独立打印合并器自己的用量，独立测量在离线那条门里用 spy 拿到），父快照的
`prompt_cache_hit_tokens=512 / prompt_cache_miss_tokens=11879` 是子任务与自己的**逐项相加**（真实网关会送
`prompt_cache_*`，离线 fake provider 不送，所以这条腿不能省）。同一时刻四个视图逐字节相同：
`{"snapshot": 16884, "summary": 16884, "persisted": 16884, "persisted_result": 16884}`；`/api/metrics` 报该工作区
`task_count=2 / subtask_rows=4 / usage.total_tokens=67207`（另一条根任务属于上一批的真实运行，不是本批）。
只读 SQL 复核在**两个口径**上都与 API 相等（工作区：root_sum 67207 == api 67207；全仓库：21 根 / 6 子行同样相等），
而**逐行相加会多算 65729**（工作区口径）——这正是 M8-T23 修掉的那一类双计，如今是量出来而不是推出来的。
把落盘行用 `from_snapshot()` 重建后再调一次 `_roll_up_tokens`：`16884 → 16884`，`restart_fold_is_noop: true`。
父任务 `cost_usd=null`（未计价不当 0）。**这一趟顺手撞出的新事实，留给 M8-T25**：同一份未计价数据，单任务说
`null`、聚合说 `cost_usd: 0.0`——两个数说的是同一件事却写成两种答案，聚合那个 0.0 读起来像「这批没花钱」，
而真话是「没人在计价表里」（`priced_tasks=0 / unpriced_tasks=2` 能推出来，但字段本身在说谎）。

**为什么这条腿必须真跑**：④ 那条「空负载 = 没有信息」的修法，风险在于真实 provider 会不会**合法地**送一个
全零 `tokens_used`。离线 fake provider 永远给不出这个形状；真机这一趟 `completion_tokens` 与
`prompt_cache_hit_tokens` 都是非零真实值，且父任务的 cache 项只能由「子 + 己」相加得到，说明真实链路走的
正是被门守住的那条路，而不是绕过去。


### M8-T25：同一个响应不能既说「不知道」又说「没花钱」——挂起项被仓库自己已有的约定结案（第十二批，2026-09-23）

**起点**：上一批真机复核顺手记下的一条 ⏳。当时判断「部分未计价时报小计还是报 null」需要客户端口径，所以
挂起。这一批先去查「这个口径到底还没定」，结果发现**仓库自己早就定过了**：`metrics()` 里 `by_model` 那段
先按 `priced` 标志把不可知的桶置 `None`，只有顶层总额漏了同一条规矩。于是不需要问任何人——
**同一份 payload 里已经有一个字段在说实话**，让另一个字段跟上它就行。「未知不当 0」这条 M8-T23 立的规矩，
适用范围原来还包括聚合自身。

**改法两条，一条都没有替客户端做价值判断**：`priced_tasks == 0 → cost_usd: null`；部分计价时数字保持原义
（已计价那部分的小计），另加 `cost_is_partial` 说清它不完整。**原先的「下界 vs 总额」二选一是被消解的，
不是被选择的**：字段含义没变，完整性是一个独立的事实，用独立字段说就好——这比在两个语义里挑一个更少武断。

**新门当场抓到我写错的那一版**：`cost_is_partial` 第一版写成 `bool(unpriced_tasks)`，于是「一条都没计价」
那格它是 `True`——「一个全未知的数被称为部分已知」，和这条要修的谎是同一类。写测试时给的是三段
（全未计价 / 混合 / 空范围），(a) 段直接判红：`assert True is False`。正确定义 `priced_tasks and unpriced_tasks`。
**先写判据再写实现，在这条上不是口号**：如果先写完实现再补测试，我很可能只写混合那一格。

**行为变更如实记下**：`cost_usd` 从「恒为数字」变成「可能是 `null`」，对假设 float 的客户端是破坏性改动。
所以先量了消费面再动手：`/api/metrics` 在 `webserver.py:324` 只有一个入口，HTML/JS 里没有它，读取侧测试只有
两处且都自备定价。README 把三种取值（数字 / `null` / 数字 + `cost_is_partial: true`）逐条写在了 `/api/metrics` 那一段。

**边界**：`priced_tasks + unpriced_tasks == task_count` 数的是**根任务行**（M8-T24 之后子任务已汇总进父行），
不是索引总行数；差额仍由 `subtask_rows` 明说。这一格没有覆盖「定价表中途改动导致历史行成本漂移」——
`cost_usd` 是在快照读取时按当前定价算的（`pricing.cost_usd(self.model, self.tokens_used)`），改了价历史任务
的读数就会变，那是 M8-T5 计价入口的既有语义，不在这一条里改。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **995 passed**（994 + 1 条口径门），exit 0。


### M8-T26：把「评委每复读一次多烧一轮 agent」的成本变成每条任务可查的事实——但停止时机一格没动（第十三批，2026-09-23）

**起点是 M8-T19 挂起理由里那句「缺的不是样本而是可满足性见证」**。上一批已经把成本钉进了断言
（`calls["agent"] == 4`：评委连返 4 次逐字相同的判定 → 4 轮完整 agent），但那钉的是**一条 fixture**；
用户真实跑一条任务，记录里只有「完成评估连续 4 轮要求继续但未收敛」这句话，看不出**从第几轮开始在复读**、
也看不出**复读的那几轮 agent 到底做没做事**。没有这两样，「要不要更早停」永远只能凭感觉辩。

**判据的两半，先各自做成可观测**：`missing + next_action` 与上一轮逐字相同 **且** `(tool 事件数, 验证次数)`
没有变化 → 发 `completion_verdict_repeated`。两半都进 `detail`（`tool_events` / `verification_runs` /
`last_verification_status` / `review_attempt`），并且显式写 `"action": "observe_only"`——**「这不是停止规则」这件事
要写在数据里，不能只写在提交信息里**，否则下一个人读到这条事件会以为停在这里。事件 `status` 用 `"ok"`：
仓库里同类「我观察到一件事」的 trace（`dependency_aware_repair_scope`）就是这么发的，与其发明一个 UI 不认识的
`warning`，不如复用已有形状（先量过事件状态值的实际分布：`ok/error/failed/skipped/...`，没有 `warning` 这一档）。

**门的强度：两半各被证明确实承重**。短路成 `False` → `assert (4 == 4 and 0 == 3)`；去掉活动比较只留 `repeats`
→ 反误杀门当场红。**反误杀那条断言形如「不存在某事件」，按 M8-T12 立下的规矩它必须自带承重证据**，所以同一个测试
里还断言了 `seen["judge"] == 4`（评委确实逐字复读了）与 `len(read_paths) >= 3`（活动确实增长了）——否则
「事件不存在」会被一个从没跑起来的场景永远满足。

**写这条反误杀门时撞到一个不在计划里的产品事实**：让只读任务的 agent **每轮真的去读一个新文件**，本以为会走到
「评委复读」，结果 `judge == 0`——完成评估**从来没被调用过**。事件序列是
`stagnation_replan → recovery_guard → task_stagnation_recovery`（两轮）后以
`Agent 在错误路径恢复阶段没有取得新的工作区证据` 结束：loop 自己的恢复保护先接管了这种「一直调工具不收尾」的形状。
**这修正了 M8-T19 那句设计的假设**：「要做须带活动信号（本轮没有新增检查类工具调用）」——在有活动信号的只读路径上，
已经有一套保护在管，评委复读只发生在 agent 每轮直接给文字结论的形状里。挂起项的原文如果不带着这条读回来，
下一步就会去修一个不是瓶颈的瓶颈。

**本批刻意不真跑模型，理由写下来而不是默认省略**：这条改动不触碰线格式、计价或用量形状（M8-T24 刚用真机量过那一层），
而真实评委在自然语言里**逐字**复读是小概率事件——花 quota 去等一次字符串相等，产出不比对同一件事的确定性断言更多。
「什么时候值得真跑」的判据仍然是：这条路径会不会因为真实的响应形状而走样。

**边界**：`completion_verdict_repeated` 只说明「本轮没有新增 tool 事件与验证」，它**不判断**本轮的模型输出是否
真的有信息量（一段新的分析文字不算活动）；把「更早停」真的做出来还需要回答「客观 grader 已通过而评委仍复读」
时该标完成还是标未收敛——那是 M8-T19 剩下的部分，本批只把它的判据材料补齐。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **997 passed**（995 + 2 条观测门），exit 0。


### M8-T27：`/api/metrics` 的各分项加起来要等于它旁边那个总数（第十四批，2026-09-23）

**起点**：M8-T24 之后手上还剩下的一把「没被量的自证句」。这一条不改代码，先量一个之前**从没被断言过**的关系：
`usage`、`cost_usd`、`by_model`、`tasks_by_status`、`subtask_rows` 是同一批行算出来的五个数，
而读者会**并排读它们**（「这笔总额是哪个模型花的？」）。M8-T23 抓到的是「总额 vs 单任务快照」不一致；
**分项 vs 总额**这一层当时没人管。

**先量再说有没有 bug**：离线探针（两个单任务 + 一个批父任务，混合计价与未计价模型）打出来的结果是
**五个数彼此一致**（`by_model` 逐 key 求和 == `usage` 的 2080/325/2405；`by_model` 非 None 成本之和 == 总额 0.00062；
`sum(tasks_by_status) == task_count == 3`；`task_count + subtask_rows == 索引行数 5`）。
所以这一批的产出是**围栏不是修复**——这一点必须写清楚，否则「新加了一条门」会被后人读成「这里曾经有 bug」。

**门**：`tests/test_logging.py::test_metrics_breakdowns_add_up_to_the_totals_they_are_shown_next_to`，
先断言形状非平凡（`task_count == 3`、两个模型、`priced=1 / unpriced=2`、`total_tokens > 0`），再断六条关系；
空范围那一格也补齐了（`by_model == {}` 且 `tasks_by_status == {}`——只断 `task_count == 0` 会让
「0 个任务但有 3 个模型」这种坏聚合器过关）。

**承重量（机械变异，两个方向各一次）**：让模型分项不再累加 token（总额仍然正确）→
`prompt_tokens does not add up across by_model / assert 0 == 2080`；让状态分项每行多计一次 →
`assert 6 == 3`。两次都只红这一条门，说明断言真的绑在「分项与总额同源」上，而不是绑在样本大小上。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **998 passed**（997 + 1 条自洽门），exit 0。


### M8-T28：三种不同的结束方式不能印成同一句话——触顶报错要说出客观验证那一侧的结论（第十五批，2026-09-23）

**起点仍是探针，不是代码**。上一批做完复读观测后，顺手把「评委触顶」这条真实轨迹整个跑了一遍
（写入 `out.txt`、假评委逐字复读）。打出来的事件轨里最要紧的一段是：

`write_file → verification_required_before_finish/error → verification_guard/error →
verifier/verification_skipped → completion_judge/completion_continue ×4 → completion_continue_capped`

也就是：**客观验证确实运行了，结论是 `skipped`（这个工作区没有可运行的检查）**。而用户看到的错误只有
「完成评估连续 4 轮要求继续但未收敛，已按上限停止；请根据缺失项检查后重新提交任务」。

**为什么这是缺陷而不是措辞问题**：这句话把责任放到了评委的missing 项上，让用户去「按缺失项再检查一遍」。
但真正可操作的事实完全不同——**没有任何可执行的验收条件存在**，所以评委从头到尾只能凭文本判断。
三种截然不同的结束（① 验证通过、评委不同意；② 没有可运行检查、验证被跳过；③ 只读任务从未触发验证）
共用同一句建议，而只有 ② 能靠「补一条验收命令」解决。这是 M8-T23 那一类「标签说谎」的最后一个尾巴：
数字诚实了，**结论的出处没诚实**。

**改法**：抽 `_unconverged_verification_note(verification_results)`，按最近一次验证状态分支成三种说法；
同时把 `verification_runs` 和 `last_verification_status` 加进 `completion_continue_capped` 的 `detail`——
**记录要能自己说明分歧在哪一侧**，不该靠人回头去数事件。

**门里的两条各自纠正了我一次猜测**：① 我先写 `verification_runs == 1`，红在 `assert 4 == 1`——
验证器是**每轮复审前都重跑一次**的，不是一次；改成断关系
`verification_runs == calls["judge"] == 4`，比较符本身写成了「同源」而不是「我记得的数」。
② 只读那一格和写入那一格必须**互相断不等同**（`assert "没有运行客观验证" not in error`），
否则一个永远返回同一句话的注解函数也能两条都绿。
**承重量**：把注解退回旧固定文案 → 两条同时红，逐字见表格行。

**刻意不动的部分**：停止时机、`未收敛` 这个词、`calls["agent"]` 的成本、任务的终态——本批改的是**结论的出处**，
不是结论本身；M8-T19 剩下的那一半（验证通过而评委不同意时该标完成还是标未收敛）仍然挂起，
但现在它在记录里是可分辨的了，这正是动手前该有的样子。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **999 passed**（998 + 1 条触顶归因门），exit 0。


### M8-T29：文档字符串承诺的门，常量写着却零处引用——命中是指针，不是摘录（第十六批，2026-09-23）

**起点是自证句清扫**，不是 bug 报告。`retrieval.py` 开头写着「secret files such as `.env` are never indexed」。
按 M8-T23 立下的规矩，这类「never」就是最该被拿去量的句子。量法是造一个真工作区，
把 `.env`、`secrets.json`、`credentials.toml`、`service-account.json`、`deploy.pem` 和正常源码放在一起，
然后问索引：`search("api key token secret")`。

**两半结论必须分开写，因为它们的严重性不同**：
① 哨兵**值**没有出现在任何命中里——`EvidenceHit` 只携带 `path / score / reason / symbols / test_failures`，
正文不进结果。所以**不存在**「检索把密钥抄进上下文」这种缺陷，报成泄漏是夸大。
② 但 `secrets.json` 是这次查询的**第一名**（12.0 分），`reason` 字段还写着 `content` 匹配过。
索引回答的是**指针**，而指针的含义就是「建议去读这个文件」——对凭据库而言，这与把它的内容端上台面等价。
③ 最脏的一半：`SECRET_FILENAMES` 全仓库**只定义、零引用**。`.env` 今天不进索引，靠的是遍历里
`name.startswith(".")` 与扩展名白名单**恰好**挡住了它。承诺有门，门是画在纸上的。

**修法里的真实取舍：同名不同物。**第一版把词干规则写成「basename 词干 ∈ {secrets, credentials} 就排除」，
自己新写的边界门立刻红在 `assert ['credentials.rs'] == []` ——那是 Rust 源码，不是凭据库。
于是加了 `_SECRET_STORE_SUFFIXES`：**只对数据文件（json/yaml/toml/ini/conf/properties/txt/无扩展名）生效**，
代码扩展名一律放行；密钥后缀（`.pem/.key/...`）本身就该挡。这条分流是门逼出来的，不是想出来的。

**门的形状**：正向那条断的是**精确集合相等**（`indexed == 五个正常文件`），不是「凭据名不在里面」——
这样误杀源码与放进凭据库两种失败都会红；再补 `files_indexed == 5` 防「索引整个空了」的假绿。
反向那条把 11 个必拦与 10 个必放行**逐名列成数据**，把规则的边界留在仓库里而不是留在记忆里。
**承重量**：把 `is_secret_filename` 短路成 `return False` →
`Extra items in the left set: 'secrets.json'、'nested/secrets.yaml'、'service-account.json'、'credentials.toml'`。

**边界（这条不覆盖什么）**：只管**索引面**。`read_file` / `grep` 这类工具能不能读凭据是**权限面**的问题，
另有一道授权门在守；改名后的凭据库（比如把 key 塞进 `db.json`）不在名字规则的能力范围内，
那需要内容级脱敏（`logging_setup.redact` 已经会遮 `sk-…`/PEM/JWT 的形状，但检索结果本来就不含正文，
所以那是另一层的活儿）；本批不假装覆盖了这些。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1001 passed**（999 + 1 条正向门 + 1 条边界门），exit 0。


### M8-T30：关自己写的边界之前先量「怎么关」——一条老门把我的修法判红了（第十五批续，2026-09-23）

**起点是 M8-T24 留下的一句边界**：「`WorkerDetached` / `_reconnect_worker` 那条支路不汇总」。看起来是个一行修复：
那里也调一次 `_roll_up_tokens`。动手前先读了镜像怎么造结果：

```python
"tokens_used": dict(snapshot.get("usage") or snapshot.get("tokens_used") or {})
```

`snapshot` 是 worker 写回的任务快照，而**已汇总的父任务，它的快照本来就含子树**。所以那句「也调一次」会把
525 变成 925。**缺口是少记，误修是多记**，而变大的数字不会自己报错——这条边界之所以还开着，一半原因正是
它没有便宜的修法。

**第一版修错了，被一条 2026-09 之前就存在的门判红**：我把声明加在 `WorkerSnapshotMirror.result()` 的**输出**上，
于是 `test_result_contract_preserves_verification_and_normalizes_both_executors` 红在
`Left contains 1 more item: {'children_rolled_up': False}`。那条门要求**线程执行器与进程执行器归一化后的结果
逐键相同**，而我在进程那一侧凭空多出一个字段。正确的落点是让**汇总自己把声明写进 `result` 负载**
（它本来就要在那里同步 `tokens_used`），两种执行器于是自然同形，契约门一行都不用放宽。
**旧门在我改代码时红了，是这套门存在的意义**：它不是为当初那个 bug 写的，却挡住了新引入的偏离。

**四段门各挡一种漂移**：(a) 带声明的负载不再相加；(b) 不带声明的负载必须补进子树；(c) 声明能穿过
`TaskResult` 与镜像、且没声明时**键根本不存在**（不是 `False`——那正是契约门红的原因）；(d) 用 AST 断言
`_reconnect_worker` 函数体里确有 `self._roll_up_tokens(...)` 调用点。前一段测的是 helper 的行为，
**helper 正确而调用点被删，聚合照样少记**——这是 M8-T23 那条接缝门（「两半边各自正确」）的同一手法，
隔了六批用在了新位置上。

**测试自己的假绿**：第一版把子任务 `TaskRecord` 建出来了却**忘了注册进 `manager.tasks`**。汇总是按 id 去索引里找
子任务的，找不到就当没有——(a) 段于是以「谁都没汇总」的姿态通过。补上注册它才真的会红。
**凡是断言「某事没有发生」的门，都要先证明它本可以发生**（这条在 M8-T12 与 M8-T29 之后是第三次生效）。

**回头更正记录**：M8-T24 叙事里那句「这条支路不汇总」就地改成「已由 M8-T30 关闭」并写清关法。
一条过期却没人回来改的边界句，读起来和仍然存在的缺口一模一样——**诚实记录包含回头修自己写下的记录**。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1002 passed**（1001 + 1 条重连四段门），exit 0。


### M8-T31：我上一批修的字段，落点写在了模型能写的那一侧（第十五批续二，2026-09-23）

**缺陷来源是我自己**。M8-T30 为了让 worker 重连不二次相加，让汇总把 `children_rolled_up` 写进 `result` 负载，
重连时读回来判断「这串数字是否已含子树」。当时觉得这正好复用主机自己的负载通道。回头看：
`result` 的内容**来自模型 / worker 的产出**，于是这条通道是双向可写的——任何被计费的一方都能在负载里放一个
`children_rolled_up: true`，让 `apply_result` 保持清零状态、`_roll_up_tokens` 直接早退，**把自己的子树花费从账单里抹掉**。
少记的方向和 M8-T30 修的那个多记一样安静：数字变小不会报错。

**判据其实早就在这个文件里**。`snapshot()` 后面钉着一句「结果负载不许覆盖主机维护的生命周期字段」，
`tokens_used` / `cost_usd` 上一批也刚被纳入同一个保护块。我只是给一个新字段选了错的一侧：
凡是**决定计费口径**的布尔，就必须和 `status` 同类，不能和 `answer` 同类。

**改法三处，缺一不可**（少任一处都留一条通路）：
① `snapshot()` 的保护块补 `children_rolled_up`；
② `TaskResult.from_payload` 把它从 metadata 透传里剔除，负载带不进来；
③ 镜像**只在快照主机字段为真时**才把声明补进负载。③ 的「只为真值加键」是刻意不对称的：
无条件写 `False` 会让线程执行器与进程执行器的负载不同形——那正是 M8-T30 被 durability 契约门判红的原因，
教训一批没忘。

**门先红给我看的是方向**：(c) 段原来断「声明能穿过 `TaskResult`」（透传是特性），改完红在
`assert None is True`——这条红是对的方向，因为它逼我把断语换成「穿不过来」，
并补上第三种负载：**只有 `result` 体里声称、快照字段却没说**的伪装负载，必须什么也换不来。
一段门的用途从「保证声明能传」变成「保证声明不能被伪造」，改的是判据而不是断言文字。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1002 passed**（条数不变；这批 strengthen 的是既有那条门的强度），exit 0。


### 第十七批 M8-T32：一个算不出来的百分比，和两种算出来但都撒谎的算法（2026-09-23）

**M4-3 挂着「`POST /api/*` 覆盖率 100%」很多批**，理由是真的：`.venv` 里没有 `coverage` 也没有 `pytest-cov`（本批实测 `ModuleNotFoundError`），装它属于改用户环境，不在这个 run 的授权范围。所以这条一直写成「按可执行口径改写」——AST 路由清单 + 各端点手写的测试。

这批想把它再推一格，先试了两种不需要依赖的算法：

| 算法 | 结果 | 为什么不能信 |
| --- | --- | --- |
| 路由名与测试里的字符串常量做双向 `in` | GET 100% / POST 100% | `/api/tasks` 与 `/api/tasks/batch` 互相满足；空串 `"" in anything` 恒真。**一个能被任何一对字符串满足的判据不是判据。** |
| 收紧成「存在以该路由为字面量的请求调用」 | GET 17.6% / POST 16.7% | 六个测试模块用 f-string 拼路径（`test_http_surface.py`、`test_allowlist.py`…），静态匹配天生看不见。**这把「我的量具看不到」读成了「产品没做到」。** |

两个数一个是假高、一个是假低，**都不是覆盖率**。剩下的可执行量法只有一个：**把每条路由真发一次请求**。

**门的做法**：从分派器 AST 取 `path == "/api/..."` 的字面量做总表（带下限与「具名路由必须在册」，防清单本身为空），GET 原样打、POST 一律打 `{}`（空对象是「绝不该把处理器打崩」的最小输入），统一要求 `status < 500`，非 2xx 必须带形状合格的稳定 code。实测 **GET 17/17、POST 12/12**，数字随测试输出打印（`MINICC_ROUTE_COVERAGE`），下次口径变了看得见。

**过程中两次自我纠正，都写进了代码注释**：
1. 先判 `/api/worktrees` 的 `worktree_error` 不合规 → 错在我的手抄白名单漏了这个码（产品是对的，400 + 结构化 body 完全守约）。
2. 于是改成「从源码收割词表」，结果红了一大片：`"code": "..."` 这个语法模式在产品里**同时**是事件 trace 的写法，收割回来的全是 `batch_finished`、`approval_requested` 之类。**从错模式派生的清单，和手抄清单一样不可信。**最终只保留「code 必须像个稳定标识符」的形状判据——它能抓住真正的违约（裸文本 404、无 code 的 500），而不假装能证明「这个码是注册过的」。

**承重量**：把形状判据换成不可能匹配的 `^ZZZ-impossible` → 3 条同时红。这条红的作用是：证明 GET/POST 两侧**确实有拒绝响应在被检查**，而不是所有路由都 200 交差。

**边界**：只覆盖精确匹配的路由（`startswith` 系的 `/api/tasks/<id>` 不在总表里）；「答了或拒了」不等于成功路径被覆盖；**这仍然不是行覆盖率**，本环境算不出那个数，也不拿这个数冒充它。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1006 passed**（1002 + 4 条路由总表门），exit 0。


### M8 退出标准真跑记录（第十八批，2026-09-23）

M1-M7 各有真跑批次，M8 的六条一直只有「任务落地」没有「标准复核」。本批按第三节 `:335-341` 逐条跑：

| 标准 | 结论 | 证据 |
| --- | --- | --- |
| M8-1 10 条消息在第 5 条 fork，两文件独立，`--resume` 能列出并恢复 | ✅ | `tests/test_session_fork.py`（与 `test_memory`/`test_plugin_api`/`test_logging` 同批 **110 passed**）；fork 独立性由 `test_two_forks_diverge_without_cross_talk` 钉住，列表面是 `minicc.main._print_sessions` |
| M8-2 任务 A 写记忆、任务 B 系统提示出现索引行；可手工编辑删除；无记忆时行为不变 | ✅ | `tests/test_memory.py`；注入面是**索引行**不是全文（M8-T1 的 token 纪律） |
| M8-3 `docs/PLUGIN_API.md` 示例原样跑通；同名注册被拒（除非 `override=True`） | ✅ | `test_plugin_api.py::test_every_doc_example_runs_verbatim` 逐 ```python``` 块 exec（不是「看起来像能跑」）、`test_late_registration_never_silently_replaces_a_builtin`、`test_override_is_explicit_and_leaves_an_audit_trail` |
| M8-4 干净 venv 装 wheel 后两个入口可用、UI 200、版本号三处一致 | ✅ | `tests/test_packaging.py` **11 passed**（含 `test_installed_wheel_serves_the_workbench`、`test_version_is_single_sourced`、`test_console_scripts_are_declared_and_resolve`），真构建 wheel+sdist，137s |
| M8-5 DEBUG 日志含 `provider_retry`/`tool_round_finished`/`run_finished` 且不含 api_key 与 web token | ✅ | `tests/test_logging.py`（含 grep 断言） |
| M8-5 `minicc/` 下 `print()` 下降 ≥80% | ✅ **98.2%**，且口径已换 | 旧注记自己说过 `grep -c 'print('` 不可信（会数到 docstring 与字符串）。本批改用 **AST 数真实 `print(...)` 调用**：`minicc/` 下 **1** 处（`cli_io.py` 的 CLI 输出漏斗），基线 55。命令：`python -c "import ast,pathlib;..."`（见下方注记） |
| M8-5 `/api/metrics` 的 token/成本与单任务快照对得上 | ✅ | 第十批 M8-T23 + 第十四批 M8-T27（分项求和=总数） |
| M8-6 `tests/test_core.py` 拆分完成、测试数不降 | ✅（一处有意残留） | 已拆成 `test_core_{agent,tools,task,llm,session}.py`（1237/309/1137/406/270 行）；残留 `test_core.py` **75 行**，文件头写明理由：`minicc.config`/`minicc.benchmarks` 不属于那五个域任一，硬塞会让文件名说谎。测试本体逐字搬迁、断言未改 |

**口径注记（`print()` 计数怎么才算数）**：`grep -rn 'print(' minicc/` 会把注释、docstring、字符串一起数进去，所以它给出的「下降 80%」既可能虚高也可能虚低。可复现的计数方式是 AST：

```bash
.venv/Scripts/python.exe -c "
import ast,pathlib
n=0
for p in pathlib.Path('minicc').rglob('*.py'):
    t=ast.parse(p.read_text(encoding='utf-8'))
    n+=sum(1 for x in ast.walk(t) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='print')
print(n)"
```

**本批结论**：M8 六条退出标准全部成立，没有一条需要改写标准来迁就实现；唯一与标准字面不同的地方（`test_core.py` 仍在）已在文件头自述理由，属于**有意保留**而不是漏拆。


### 第十九批 M8-T35：一句「口径可复现」拆出两个缺陷，其中一个能让 100% 变得毫无意义（2026-09-24）

上一批把 `coverage[toml]` 装进 dev extra，M4-3 那条挂了几批的「算不出来」当场结案，理由写得很硬：「① 模块行覆盖 74.5%；② 分派点覆盖 GET 20/20、POST 14/14 = 100%……**M4-3 的标准说的是②**，所以这条按 100% 成立、且口径可复现」。

这批只做一件事：**把「可复现」当成判据去执行一次**——从仓库里能找到的东西出发重算 ②。

**缺陷一（复现不出来）**：仓库里那两条命令（`coverage run … -m pytest …` + `coverage report`）只能得到 ①。② 需要一个把「AST 里每条路由自己的比较语句行号」映射到覆盖率 JSON `executed_lines` 的脚本，而它当时住在 `C:\Users\…\Temp\route_cov.py`，文件头写着「不提交，这是量法不是门，可复现命令在 ROADMAP 里」——ROADMAP 里并没有那条命令，`coverage json` 这一步在整个仓库中没有任何一处提到。**「可复现」和「我这台机器上刚跑过」是两件事**：上一批的提交信息里我写了 "the measurement is reproducible"，这句话的承重部分不在依赖声明里，在量法本身有没有进仓库。

**缺陷二（量法可以被一次请求喂满）**：② 的定义是「这条路由的比较行执行过没有」。`minicc/webserver.py` 的 `do_GET`/`do_POST` 是平铺的 `if path == "/api/x": …; return` 链，**任何一条走到链尾的请求都会把整条链上的比较行点亮**。没有停在推理上，直接量：只跑 `test_post_unknown_api_route_is_404`（它只发一个 `POST /api/nope`）——

```
POST: A(compare-line-ran)   14/14 = 100.0%
      B(branch-body-ran)   0/14 = 0.0%
```

**一条从未命中任何路由的请求，就能让「POST 路由覆盖率」报 100%。**这和第十七批那两个静态匹配数是同一类错误（一个假高、一个假低），只是这次撒谎的是**运行时**量具，所以更不容易被看出来：它确实执行了代码，只是执行的那一行并不能证明被分派过。判据换法：一门量具要问的不是「这一行跑过没有」，而是「**这个分支体进过没有**」——分支体内的语句行只有控制流进入该分支才会执行，喂不满。

**换口径后结论未变**：B 侧同样 GET 20/20、POST 14/14，选定测试集为 `test_http_surface.py + test_http_route_inventory.py`（故意不扩到全量：全量的口径回答的是「 somewhere 碰过」，正是这次要防的那种弱化）。所以这条**不是被推翻**，是证据从撑不住的换成撑得住的。

**同一类错在这批里当场撞了第二次**：第一版量具只读 `If.test` 整体，而 `if path.startswith("/api/tasks/") and path.endswith("/events")` 的 test 是 `BoolOp`，于是 34 条真分派点静默变成 31 条——**GET 19/19、POST 12/12，两个数照样都是 100%**。分母塌了 3 条而百分比毫无反应，正是 M8-T32 那条教训的运行时版本。抓它的办法不是「更仔细地写 AST 遍历」（同一个遍历写不出发现自己看不见的东西），而是**再养一个笨阅读者**：`text_predicates()` 只按行正则匹配 `path ==/startswith/endswith "/api/..."`，与 AST 阅读者对账，谁少 seen 一条就报 `INVENTORY PROBLEM` 而不是报百分比。

**门的承重量（逐字）**：
- 把 B 退化回 A（`entered` 改读 `compare_line`）→ 2 条红：`assert 0 == 1`、`assert 4 == 0`；
- 把 `_test_predicates` 从 `ast.walk(test)` 换成只看 test 整体 → **6 条红**，其中端到端那条的失败输出同时印着 `INVENTORY PROBLEM: webserver.py:355/566/570 compares \`path\` against '/api/tasks/' in plain text but no dispatch site claims it` **和** `31/31 = 100.0%`——一句话里既有「100%」又有「我的清单不全」，这就是为什么这条只能靠退出码守，不能靠人读输出。

**顺手修掉的过期句**：`tests/test_http_surface.py` 里那段注释还写着 "No coverage tool is installed here and CI does not run one, so that percentage cannot be computed"——`coverage 7.16.1` 已经在 dev extra 里，这句话现在是假的。改成写明两道门各自量什么、以及「比较行跑过」为什么不等于覆盖。

**边界（这批不声称的东西）**：① B = 100% 只说明「每条路由的分支体至少有一行被某个请求执行过」，不说明每条路由的**成功路径**有断言（那仍由 `test_http_route_inventory` 的响应契约与 `test_http_surface` 各自的终态断言承担）；② `--check` 目前只有本地与测试内调用，**没有接进 CI**——往流水线加步骤会影响别人 push 的 CI，不在本 run 里替用户决定；③ 模块行覆盖 74.5% 依然单独报，不冒充 ②；④ 这套量具读的是 `executed_lines`，`[tool.coverage.report] exclude_also` 那两条排除规则作用在报告阶段，实测未影响分派点集合（34/34 与逐条枚举一致）。

**基线**：全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1018 passed**（266.32s，exit 0；上一批 M8-T34 没有留全量数字，只留了文件内的 9 passed / 合计 86 passed，所以 1006→1011→1018 这一格中间点是推算的、已就地标明）。本批新增 7 条门全在这趟里跑过；其中端到端那条会在测试内 spawn 一个 `coverage run -m pytest …` 子进程，**别把这种自派生的子进程数成「本机并行 run」**——M1-1 行记了这次误判的原文。


### 第二十批 M8-T36：一句指向不存在段落的「见」，和一份只有我自己抄过的手写清单（2026-09-24）

上一批的主题是「一个百分比可以被一次请求喂满」。这批换了个看起来不重要的对象——**文档里的交叉引用**——结果同一个失效模式又出现了一次，而且这次是它先找到我。

**触发点**：`docs/ROADMAP_TO_PRODUCT.md:754` 那行 M8-T34 记录，上一批（M8-T35）我重写它来描述「它指向一个不存在的段落」，而重写后的句子里**又原样带着** `见下方「第十八批 M8-T34」`。人（和我）校对不出自己刚写下的这句话；这句话的承重部分是「去那一节看证据」，而那一节是 M8 退出标准的总表，里面没有 M8-T34 的小节。这类东西和 M8-T29 那条「常量写着却零处引用」是同一类：**看起来像证据，实际上不指向任何地方**。

**做法**：`scripts/doc_pointers.py`，一条命令复现（`python scripts/doc_pointers.py --check`），并给它 13 条门（`tests/test_doc_pointers.py`）。两条判据：

1. **定位符要落在存在的标题上**。`第N批` 匹配批次小节标题里的字样，`第N节` 先做中文数字归一再映射到 `N、…` 的二级标题，`附录 X` 匹配附录小节；`见/参见` + 方向词（下方/上方/文末/本节…）+ 可选 `「…」`。
2. **指针同时点名编号时，那个编号必须在那一节里被「声明」**——声明=出现在标题文本或表格行的**首格标签**里，不是出现在正文里。这条是这批最值钱的一步：最初版本写的是「该编号在那一节里出现过吗」，而 `见下方「第十八批 M8-T34」` 这句话本身就把 `M8-T34` 拼了出来，于是**指针自己回答了自己的问题**，`见 M8-T999 行` 一样通过。这与上一批「比较行执行过」是同构错误：判据的答案写在判据的输入里。

**中文让 `见` 不能当标记**。第一版按 `见` 抽取，48 条命中里几乎全是「可见 / 意见 / 见证 / 预见 / 见收益」。改成只收「span 里带定位符或编号形状」的片段；剩下的仍然计数并打印成 `unresolved`（当前 **84** 条），因为「这句话没被任何门守住」是**已知的空白**，静默丢弃会把它伪装成干净。

**实测口径（原样输出）**：`checked 33 pointers (84 spans name no locator) and 21 links in 19 documents`，exit 0（**这是插入本批记录之前**的数；插入后同一条命令报 35 条指针 / 22 条链接，而 `unresolved` 那一格每次都变——两个数都随文档增长而变，所以下限才压在实测之下）。分布：roadmap 30 条指针 / 2 条链接，README 1 / 7，`AUDIT_2026-09-20.md` 2 / 2。两个下限（`MIN_POINTERS` roadmap=15、`MIN_LINKS` roadmap=1 / README=3）**刻意压在实测之下**：它们要防的是阅读器瞎掉时报假绿（上一批 34→31 而两个数照样 100% 的那个教训），不是防措辞改动。

**量出来的 4 条真悬空引用**（先在内存里还原原文复测，再改文档；括号里的行号是**插入本批记录之前**的实测位置，插入之后会后移，这正是行号不该被当成身份的原因——判据用的是「文档 + 定位符 + 编号」而不是行号）：

```
[POINTER] ROADMAP_TO_PRODUCT.md:939 「第四节 M4-3 那条同类先例）」 说 M4-3 在「四、明确不做什么（以及为什么）」里，那里没有这个编号
[POINTER] ROADMAP_TO_PRODUCT.md:1091 「第四节 M1-1 行）」 说 M1-1 在「四、明确不做什么（以及为什么）」里，那里没有这个编号
[POINTER] ROADMAP_TO_PRODUCT.md:754 「第十八批 M8-T34」 说 M8-T34 在「M8 退出标准真跑记录（第十八批，2026-09-23）」里，那里没有这个编号
[POINTER] README.md:289 「审核文档第十二节」 指向不存在的第十二节
```

前两条最有意思：`第四节` **解析成功**了（第四节确实存在，是「明确不做什么」），错的是它后面点的编号——一个定位符存在、内容却对不上的引用，比找不到标题的引用更难靠人眼发现。第三条是原始触发点，且它的红不是「第十八批不存在」，而是「第十八批那一节里没有把 M8-T34 登记成标题或行标签」，正是判据 2 相对判据「出现过」强出来的那一格。第四条是跨文档：`见审核文档第十二节` 没把文件名写进指针，工具只能在本文件里找第十二节，于是报不存在——修法是**把文件名写进去并做成真链接**（`[docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md) 第十二节`），而不是放宽门。

上面那四行是把旧文本在内存里还原后打印的一次性结果，脚本没提交（Temp 里的东西不算复现路径，上一批刚为这句话付过代价）。**仓库内的复现路径**是 `tests/test_doc_pointers.py` 里的 `_BAD_DOC`：同一 shape（指向一个存在却没登记编号的批次）的微缩版，断言它恰好产出一条点名 `M8-T34` 与「第十八批」的 complaint；外加端到端那条门真的执行 `scripts/doc_pointers.py --check` 并检查 exit code。

**门是活的，用变异证明而不是用断言证明**：
- 去掉 `_mask_code`（工具不再把代码区间当引用）→ `3 failed, 10 passed`，红的是 `test_shipped_documents_have_no_dangling_references`、端到端那条和新加的「引用不是断言」。这一条顺带量出一个事实：**仓库里确实存在写在反引号里的指针**，所以掩码不是我为自己的错误找的台阶，它改变结论。
- 手写清单的对账：把某个模板的后缀打错 → 同时报「前缀族没有模板」与「模板后面没有分支」；多塞一条源码里不存在前缀的模板 → 报幻影探针；给 `_CATCH_ALL` 一条空 reason 或让它的 pattern 不再匹配任何东西 → 红。两次变异后 `scripts/doc_pointers.py` / 清单都按字节还原（`restored: True`）。

**这批我自己犯的三次同类错**（都留在门的注释里，因为它们正是门要防的东西）：
1. 抽取 `_DYNAMIC_ROUTES` 的 AST 只认 `ast.Assign`，而它在测试里写着 `x: dict[str, list[str]] = {...}`（`ast.AnnAssign`），于是干净检出也报「手抄清单没了」——**一个只按自己写法找东西的阅读者，会把别人的正确写法读成缺失**，和上一批 `BoolOp` 那次同源。
2. 编号检查最初 `identifier in text`（自我满足）。
3. 新加的「代码引用」门断言 `unresolved == 1`（我以为引用会算成「没解析的标记」），实际掩码把整段连标记一起抹掉，`checked=0, unresolved=0`；改成 `== 0` 之后我又把 `sum("第十八批" in p.detail) == 1` 当作「分辨哪条 complaint  fired」的手段，而**每条 detail 都整段引用了那个 span**，于是要么 2 要么 0，永远不是 1。三次都是**期望错，不是工具错**：按上一批定下的口径，归因要用能区分个体的字段（这里是 complaint 的断言动词「指向不存在的段落」vs「没有这个编号」），不能用计数代理。
4. （附带）按文件路径加载脚本时，模块内联的 `@dataclass(slots=True)` 会在 `exec_module` 里抛 `AttributeError: 'NoneType' object has no attribute '__dict__'`，除非先把模块注册进 `sys.modules`。测试的 `_load()` 早就这么做了，我这批在 Temp 里复现红字时又踩了一遍——说明这条不是假想故障。

**边界（这批不声称的东西）**：① 只有「名字里带定位符或编号」的指针可查，`口径见下方注记` 这类完全查不到，打印出来的那批 `unresolved` 就是明写的空白面积；② 「声明在标题或行标签」证明编号**登记在那个落点**，不证明那句话对内容的描述正确——语义仍然要人读；③ 代码区间整体屏蔽，代价是写在反引号里的真悬空引用同样看不见；④ 跨文档指针必须在指针里指名文件，否则只在本文档解析；⑤ 链接只验「目标在磁盘上存在」，不验锚点；⑥ 两个 `--check`（本工具与 `route_coverage.py`）都只由测试内部与本机调用触发，**没有接进 CI**——往流水线加步骤影响别人 push 的构建，留给用户决定。

**基线**：本批新增 17 条门（doc pointers 13 + 路由清单对账 4），全量数字见上表末格。


### 第二十一批 M8-T37：行内代码里的每条路径、每个行号、每个测试名都是一条断言（2026-09-24）

**触发点**：上一批把 `见/参见` 和 markdown 链接变成了断言，然后本批第一条真跑就把 HEAD 的脚本翻出来看——`grep -c _EVIDENCE_TABLES` 在 HEAD 是 **0**。也就是说：文档写着「验收见下面这一行」，而**没有任何东西去那个文件里找过这个函数**：

```text
验收：tests/test_task_worker.py::test_worker_survives_host_restart
```同一个仓库里最容易被当成事实的句子，是那些用反引号包起来的定位符。

**判据（写进代码的口径）**：代码片段里的这五种形状是断言——路径、`路径:行号`、`路径.ext.属性`、`测试文件.py::测试函数名`、裸 `test_*`；断言就要能被满足：文件必须存在、行号不得越过文件末尾、`::` 右边的测试必须**定义**在那个文件里（不是"文档里出现过"）、属性名必须出现在被引文件中。另外补**第二阅读器**：不带反引号、但带斜杠且能命中仓库文件的正文路径同样算断言（本批实测 17 条走这条路）。

**本批起点是 28 条红 / 21 条不重复断言**。复现配方（一次性脚本，不在仓库里）：

```text
git worktree add ../t37-probe HEAD          # 用 HEAD 的文档，不是本批改过的
# 把 scripts/doc_pointers.py（本批版本）复制进去，import 后对 _EVIDENCE_TABLES
# 里六个字典逐个 .clear()，再对 19 份文档跑 check_evidence()
```

清空豁免的理由是：**不先看清"如果什么都不放过会怎样"，就没资格说某条被放过**。逐字转写（顺序即输出顺序）：

```text
 1 AUDIT_2026-09-20.md:426 web/app.min.js 指向的路径在仓库里不存在
 2 GAP_ANALYSIS_AND_ROADMAP.md:192 web/src/01-core-state 指向的路径在仓库里不存在
 3 GAP_ANALYSIS_AND_ROADMAP.md:193 web/app.min.js 指向的路径在仓库里不存在
 4 ROADMAP_TO_PRODUCT.md:26 docs/SECURITY_CHECKLIST.md 指向的路径在仓库里不存在
 5 ROADMAP_TO_PRODUCT.md:54 tests/test_p0_p1_p2.py::test_recovery_required_does_not_loop_on_plain_text 没有这个测试：它定义在 test_m1t1_recovery_required_does_not_loop_on_plain_text
 6 ROADMAP_TO_PRODUCT.md:62 tests/test_stream_merge.py 指向的路径在仓库里不存在
 7 ROADMAP_TO_PRODUCT.md:91 docs/SECURITY_CHECKLIST.md 指向的路径在仓库里不存在
 8 ROADMAP_TO_PRODUCT.md:205 benchmarks/fixture-workspaces/ 指向的路径在仓库里不存在
 9 ROADMAP_TO_PRODUCT.md:207 test_grader_unreadable 既不是测试文件名也不是任何测试函数名
10 ROADMAP_TO_PRODUCT.md:221 web/app.min.js 指向的路径在仓库里不存在
11 ROADMAP_TO_PRODUCT.md:222 web/app.min.js 指向的路径在仓库里不存在
12 ROADMAP_TO_PRODUCT.md:345 minicc/agent/memory.py 指向的路径在仓库里不存在
13 ROADMAP_TO_PRODUCT.md:402 web/app.min.js 指向的路径在仓库里不存在
14 ROADMAP_TO_PRODUCT.md:627 tests/test_task_worker.py::test_worker_survives_host_restart 没有这个测试：整个 tests/ 里没有这个函数
15 ROADMAP_TO_PRODUCT.md:630 benchmarks/fixture-workspaces/ 指向的路径在仓库里不存在
16 ROADMAP_TO_PRODUCT.md:632 test_real_dataset_clears_floor 既不是测试文件名也不是任何测试函数名
17 ROADMAP_TO_PRODUCT.md:634 web/app.min.js 指向的路径在仓库里不存在（同一行三处）
20 ROADMAP_TO_PRODUCT.md:664 minicc/permissions.json 指向的路径在仓库里不存在
21 ROADMAP_TO_PRODUCT.md:676 minicc/web_static 指向的路径在仓库里不存在
22 ROADMAP_TO_PRODUCT.md:676 minicc/ide_static 指向的路径在仓库里不存在
23 ROADMAP_TO_PRODUCT.md:715 tests/test_core.py:1510 在第 75 行之外（文件只有 75 行）
24 ROADMAP_TO_PRODUCT.md:753 tests/test_http_route_inventory.py::test_prefix_dispatched_families_are_declared_not_silently_omitted 没有这个测试：整个 tests/ 里没有这个函数
25 ROADMAP_TO_PRODUCT.md:772 test_worker_survives_host_crash 既不是测试文件名也不是任何测试函数名
26 ROADMAP_TO_PRODUCT.md:837 test_worker_survives_host_restart_and_continues_long_stream 既不是测试文件名也不是任何测试函数名，最接近的是 test_worker_survives_host_crash_and_continues_long_stream
27 README.md:137 minicc/web_static 指向的路径在仓库里不存在
28 README.md:137 minicc/ide_static 指向的路径在仓库里不存在
```

**逐条分派，没有一条静默吞掉**（8 条改文档 + 13 条登记豁免 = 21 条不重复断言；13 条引用落在 9 个豁免键上）。八处文档确实写错了，改法都是"指向真实存在的那个名字"（左边是 HEAD 原文，右边是现在的文本）：

```text
:54   tests/test_p0_p1_p2.py::test_recovery_required_does_not_loop_on_plain_text
  ->  tests/test_m1_integrity.py::test_m1t1_recovery_required_does_not_loop_on_plain_text
      文件在 M8-T6 拆分时改名，前缀 test_m1t1_ 也一起丢了
:207  test_grader_unreadable                    ->  test_grader_unreadable_by_file_tools
:627  …::test_worker_survives_host_restart      ->  …::test_worker_survives_host_crash_and_continues_long_stream
      并补括注「M4-T1 时该名不带 crash_and_continues_long_stream，M8-T14 换的名」
:632  test_real_dataset_clears_floor            ->  test_real_dataset_clears_floor_backing_the_written_conclusion
:664  minicc/permissions.json                   ->  工作区 .minicc/permissions.json（包内路径从来不放规则）
:753  …_are_declared_not_silently_omitted       ->  …_are_probed_or_parked_with_a_reason
:772  test_worker_survives_host_crash           ->  test_worker_survives_host_crash_and_continues_long_stream
:837  「原测试 test_worker_survives_host_restart_and_continues_long_stream 用 shutdown() 模拟重启」
  ->  同一个死名字**从反引号里移出来**（见下条模式），不改成活名
```

**修法里唯一一条不是"改成对的"的**：`:837` 那一句的任务就是记录"原来的测试名不再成立"，把它改成新名反而毁掉这句话。于是确立一条可复用的规则——**要提一个已经死了的名字时，死名字写在正文里、活指针放在反引号里**：读者只校验代码片段，正文第二阅读器只校验带斜杠的路径，历史因此留住而悬空指针不出现。这条规则是量具自己教我的：本批给 README 写这段说明时，形状示例 file.py::test_name 反手被自己判红一条 `DANGLING EVIDENCE README.md:315`，改写成正文才过。

**13 条语义已变的引用落在 9 个豁免键上**，六类理由各自的判据不同：不是仓库路径（9 键）、构建产物（`minicc/web_static`、`minicc/ide_static`：setup.py 的 build_py 构建期复制进来）、计划承诺但未交付（`docs/SECURITY_CHECKLIST.md`、`tests/test_stream_merge.py`、`benchmarks/fixture-workspaces/`——**都是"某个退出标准要求的文件从未建立"，登记理由必须指名是哪一条退出标准**）、被引用来说明它已过期（`tests/test_core.py:1510`、M8-T6 拆分留下的整段失效引用登记）、主动退役（`web/app.min.js` 由 `tests/test_cleanup_version.py::test_app_min_js_retired` 断言它不再存在；`web/src/01-core-state` 由 `a97bf13` 的分片重组消掉）、计划里否掉的拼法（`minicc/agent/memory.py`，交付走的是 `minicc/tools/memory.py`）。**【M8-T38 更正】** 这 9 个"不是仓库路径"的键里有 **5 个是死行**（`AGENTS.md`、`CLAUDE.md`、`MINICC.md`、`review.md`、`keys.md`——不带斜杠的裸文件名按上一批自己立的规则不构成定位符断言，因此这五个键从来没有被咨询的机会），实际答上过引用的只有 4 个；本批的豁免表活性门量到并已删除，见第二十二批。

**豁免必须自己付账**，两道检查各挡一种腐烂：理由为空 → 报「没有理由」；已无任何文档引用 → 报「陈旧登记」。空豁免比没豁免更坏：它让一条断言看起来被审过。

**本批量具自己造的两处缺陷，都是它自己的门抓的**：

1. **清单双计**——加了「先计数」的全局 `checked += 1` 却没删掉三个分支里原有的 `checked += 1`，一个 span 计两次；工具当场打印 **1524** 条，真值 **794**（都是当时那份清单）。抓到它的是新写的 `_evidence()` 助手第一条断言（它断言的就是自己的计数）。这类"派生数字没有再量一次"的错误在 M8-T29、M8-T35 各红过一次，这次是第三次。
2. **策略表里的死行**——`_RESOLVE_ROOTS` 五条里四条**零调用点**（实测 `<root> 544 / tests 2 / minicc 0 / scripts 0 / docs 0 / 兄弟目录 0`），因为 `_is_path_claim` 拒掉了每一个缩写头，而 `scripts`、`docs` 开头的引用本来就已经从仓库根算起。这就是 M8-T29 那条「零引用常量」换了我的工具的衣服：一张看起来像策略的表，读者不会去问它有没有被走到。修法是把缩写真正解析起来（`web/src` 一路补上），删掉不可达的行，并新增一条**反向门**：每个解析根都必须至少答上一条在仓文档里真出现过的引用——死行的判据是"没人走到"，不是"注释说它该在"。

**门是活的（六条变异，逐条 sha256 `71b05709db84` 字节还原并复验）**：

| 变异 | `--check` | 门 |
| --- | --- | --- |
| ① 豁免永不生效（`if False and _exemption(...)`） | exit=1，逐字 `:205`、`:630` 报 `benchmarks/fixture-workspaces/ 指向的路径在仓库里不存在`、`:715` 报 `tests/test_core.py:1510 在第 75 行之外（文件只有 75 行）` | 4 failed / 18 passed（floors、shipped-docs、端到端、正文第二阅读器） |
| ② 先豁免再计数 | exit=1，`INVENTORY README.md:1: 只 harvest 到 8 条…低于下限 12` | 3 failed，第三条逐字 `assert 1 == 3`（豁免过的引用不再被算作"读过"） |
| ③ 关掉「豁免必须带理由」 | exit=0（只有门能抓） | 1 failed，集合少了 `没有理由` 那一条 |
| ④ 登记一个无人引用的豁免键 | exit=1，`DANGLING EXEMPT … 已无任何文档引用，是陈旧登记` | 2 failed |
| ⑤ 删掉 `web/src` 解析根 | **exit=0** | 1 failed，`assert 2 == 3`（反向活性门） |
| ⑥ 正文阅读器不再要求带斜杠 | exit=0 | 1 failed，`loop.py` 被当成了断言 |

⑤ 与 ⑥ 值得单独说：`--check` 全绿而门红，说明**"跑一遍命令 exit 0"永远不足以证明一个判据存在**——这条也正是 ① 那类豁免能藏住东西的原因。

**还有一条假绿变异，是本批最贵的教训**：③ 的第一版我写成「在 `_RETIRED_PATH` 字典字面量开头插一个空理由键」，跑完 `--check` exit=0、22 条门全绿——**同一个键在下一行又被赋了一次值，空理由根本没落地**。一次不改变任何行为的变异，是对门的零证据。此后变异驱动强制三件事：锚点 `count == 1`、写盘前 `compile()`、还原后复验摘要。

**当场纠正上一批写下的断言**：第二十批说「`scripts/doc_pointers.py --check`，实测 19 份文档、`--check` exit 0」。在干净 worktree 里检出 HEAD 跑同一条命令，**exit=1**：`OPTIMIZATION_DELIVERY_2026-09-18.md:72/74` 两条 markdown 链接指向 output/playwright 下两张 png，而 `.gitignore` 第 10 行忽略了整个 output 目录——**本机存在、不进仓库**，所以那条命令的绿是作者机器的绿，不是仓库的绿。本批没有去修它（那是链接阅读器，不是本批的证据阅读器；修它要先决定"生成产物的链接"算不算断言），**列为下一批第一项 M8-T38**，两个候选：给链接侧补与证据侧同形的豁免（带理由 + 仍被引用），或把该文档里那两条链接改成"跑某条命令后本地生成"的散文。**M8-T38 现在有两件而不是的一件**：第二件是本批末尾量出来的「同一 HEAD 的清单在干净检出是 782 条、在开发机是 811 条」，根因在形状判据读工作目录（见下文「当前实测」段）——两件同源：**量具把"我这台机器上有什么"当成了"仓库里有什么"**。**顺带一条方法论**：凡引用"某命令 exit 0"作为退出证据，必须同时在干净检出里跑一次——否则它证的是我的磁盘。**【M8-T38 结案】** 上面两个候选采纳的是第一个（链接侧补判据），但没有写豁免理由而是改成现场问 `git check-ignore`——判据来自仓库自己的忽略规则，不需要有人记得抄。

**边界（明确不声称）**：围栏代码块内部、代码片段内部的悬空指针看不见（这是"反引号里是引用不是断言"那条规则的代价，本批已用 ① 的第三条红量化过一次）；`_SNAPSHOT_DOCS` 只跳行号检查、`_OUT_OF_SCOPE_DOCS` 整篇跳过；无扩展名的模块名与裸文件名不算断言（`127.0.0.0/8`、`--session-id/--resume`、`tools/call`、`loop.py` 都会被误判，故显式判"非断言"并各有门）；`_PATH_REF` 认的扩展名是白名单，新语言文件类型要显式加；**`--check` 仍未接入 CI**（与本批开头那条"没人去文件里找过那个函数"是同一件事的制度化版本，接 CI 需要用户批准）。**当前实测**（本批记录定稿时）：`checked 37 pointers (95 spans name no locator), 22 links and 811 evidence pointers (17 path claims sit outside code spans) in 19 documents`；roadmap 576 条 / README 18 条，下限分别 200 / 12。这段记录自己就贡献了 17 条新断言——每写一段证据，清单就长一次，所以这两个数只能"定稿时测"，不能抄。**而且它连"在哪台机器上测"都敏感**：同一份 HEAD 在干净 worktree 里跑同一条命令是 **782 条 / 16 条正文断言**，本机是 811 / 17。差的 29 条不是文档内容不同，而是 `_top_level()` 读的是**工作目录的列目录结果**——output、.minicc 这类被 gitignore 的目录只在"跑过东西的机器"上存在，于是指向它们的引用在开发机上是断言、在干净检出里被当成"不是仓库路径"直接不算。这条量具的清单因此不是 HEAD 的函数，M8-T38 要一并修（可接受的头部要从被跟踪的内容推出来，而不是 iterdir）。**【M8-T38 已结案】** 修完后同一条命令在这台开发机上是 **782 / 16**，与上一批在干净检出量到的读数相同；上面那句"当前实测 811 条 / 17"不是文档的内容，是一块磁盘的内容——往干净 worktree 里只种四个 gitignore 目录，旧脚本就原样打出 811/17，逐字四格见第二十二批。

**承重量**：本批新增 9 条门（`tests/test_doc_pointers.py` 13 → 22）、全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1044 passed**（217.20s，exit 0；上一基线 1035，差额恰好等于新增门数 9，说明没有旧门被改掉或跳过）。

### 第二十二批 M8-T38：一份清单如果取决于"哪台机器克隆了仓库"，就不能拿来当退出标准（2026-09-24）

**触发点**：上一批结尾同时留下两件事，而且当场判定它们同源——「量具把"我这台机器上有什么"当成了"仓库里有什么"」。第一件是 `--check` 在干净检出 exit=1（作者机器 exit=0）；第二件是同一份 HEAD 的证据清单在开发机 811 条、在干净检出 782 条。本批把这两件一起结案。

**判据（写进代码的口径）**：**任何从文件系统推出来的集合，都必须从 git 索引推出来**。具体是三处：

1. 目录头（决定"一段带斜杠的文本算不算仓库路径断言"）从 `git ls-files` 返回的路径前缀推出，不再 `iterdir()`。实测 HEAD 的 `iterdir` 版给出 **19 个头**，其中 **11 个只在这台机器上存在**：

```text
HEAD _top_level() (iterdir)  : 19 ['.git', '.github', '.minicc', '.playwright-cli', '.pytest_cache',
                               '.ruff_cache', '.venv', 'benchmarks', 'build', 'dist', 'docs', 'ide',
                               'minicc', 'minicc.egg-info', 'node_modules', 'output', 'scripts',
                               'tests', 'web']
index-derived heads          : 8 ['.github', 'benchmarks', 'docs', 'ide', 'minicc', 'scripts', 'tests', 'web']
iterdir-only heads           : 11 ['.git', '.minicc', '.playwright-cli', '.pytest_cache', '.ruff_cache',
                                   '.venv', 'build', 'dist', 'minicc.egg-info', 'node_modules', 'output']
claims under disk-only heads : 64 Counter({'.minicc': 33, 'output': 28, '.venv': 3})
```

那 64 条引用就是 29 条清单差的来源（一条 span 可以在多个文档里出现，去重后按形状判据另算）。`_abbreviation_heads()`、`_resolve_path()`、`tests/` 下的模块名清单也一并改成读索引（`_holds()` 一个入口，`scripts/doc_pointers.py:641`）——**同一个坏味道不可能只在一处**。

2. 链接判据从二态换成**三态**：被跟踪 → 绿；被 gitignore → 记为 `generated`（照计数、照在总结行里打印、不报红）；**本机有但 git 没跟踪 → 也算红**。第三条是本批新加的，方向与第一条相反：前两条挡的是"我的绿是假的"，这一条挡的是"只有作者看得见的断链"——如果只判存在性，我在本地新建一个没 `git add` 的文件、文档里指它，`--check` 会一直绿到我推送那天。

3. **不在工作树里就没有索引**，此时退回存在性判断。这条不是为了兼容而写的，是为了让 `tests/test_doc_pointers.py` 里那些 `tmp_path` 合成仓库继续可测——它们没有索引，硬套判据②会把门变成"必须在真仓库里跑"，那样门本身也依赖环境了。

**四格实测（在同一个干净 worktree 里跑完，`git worktree add` 检出 HEAD，把待测脚本复制进去，跑完 `worktree remove`；不动工作区、不 stash）**：

```text
tracked files in the clean worktree: 228
--- A HEAD's script, clean worktree: exit=1
    DANGLING LINK OPTIMIZATION_DELIVERY_2026-09-18.md:72: 链接目标 ../output/playwright/optimized-1440-light.png 不存在
    DANGLING LINK OPTIMIZATION_DELIVERY_2026-09-18.md:74: 链接目标 ../output/playwright/optimized-390-dark.png 不存在
    checked 37 pointers (95 spans name no locator), 22 links and 782 evidence pointers (16 path claims sit outside code spans) in 19 documents
--- B fixed script, clean worktree: exit=0
    checked 37 pointers (95 spans name no locator), 22 links (2 of them into git-ignored generated output) and 782 evidence pointers (16 path claims sit outside code spans) in 19 documents, over 228 tracked files
--- C HEAD's script, generated dirs planted: exit=1   （红 32 条，逐字见脚本输出，节选）
    DANGLING EVIDENCE AUDIT_2026-09-20.md:84: .venv/Scripts/python.exe 指向的路径在仓库里不存在
    DANGLING EVIDENCE GAP_ANALYSIS_AND_ROADMAP.md:159: output/evaluation.json 指向的路径在仓库里不存在
    DANGLING PROSE docs/PROJECT_REVIEW_2026-09-18.md:1: 散文里（反引号之外）写着路径 output/evaluation-full.md，仓库里没有，而且阅读器看不见它
    DANGLING LINK OPTIMIZATION_DELIVERY_2026-09-18.md:74: 链接目标 ../output/playwright/optimized-390-dark.png 不存在
    checked 37 pointers (95 spans name no locator), 22 links and 811 evidence pointers (17 path claims sit outside code spans) in 19 documents
--- D fixed script, generated dirs planted: exit=0    （与 B 一字不差）
```

C 格是本批最想要的一格：只往那份**干净检出**里种四个 gitignore 的目录（`output/playwright/` 下两张 png、`.minicc/`、`node_modules/`、`.venv/`），旧量具的清单就从 782/16 变成 **811/17**——和我开发机上的读数一字不差。于是"811 条证据"这句话被彻底定性：**它从来不是文档的内容，是磁盘的内容**。更难看的是它的红集合也跟着换了一批（A 格 2 条链接，C 格 32 条，其中 30 条是刚被"看见"的 `output/…` 证据与 1 条 `.venv/…`），也就是说旧量具在四种环境里给出**三种不同答案**——「跑一遍 `--check` 得到 exit 0」作为退出标准在这套判据下根本不成立。修复后 A 与 D 相同、B 与 C 相同，清单只剩 HEAD 一个自变量。

**分类不是赦免**：那两条 png 链接我没有写进豁免表。豁免表要人手抄理由、而且要人记得抄；而"这是生成产物"仓库自己知道——`.gitignore` 里写着。所以判据是现场问 `git check-ignore`，回答"是"就归 `generated`，将来 `.gitignore` 改了判据自动跟着改。**代价也要写清**：这条判据依赖 git 可用；`_git_output()` 失败时返回空清单，而空清单会被 `main()` 里那条 `INVENTORY` 门当场报红（"git ls-files 一条都没返回"），不会静默变成"什么都不用检查"。

**量具自己上一批留下的死行，被本批新门抓出来**：M8-T37 刚把「一张看起来像策略、却零调用点的表」写成教训，本批的豁免表活性门就在同一张表里量到 **5 个零命中键**：

```text
零命中（已删）：AGENTS.md  CLAUDE.md  MINICC.md  review.md  keys.md
修完实测：六类共 14 键，14 个全部命中 ≥1，合计答上 75 条引用
          _NOT_A_REPO_PATH 4 键/43 条、_BUILD_OUTPUT_PATH 2/6、_PROMISED_PATH 3/8、
          _QUOTED_STALE_PATH 2/5、_RETIRED_PATH 2/11、_DECLINED_PATH 1/2
```

为什么它们零命中：不带斜杠的裸文件名在判据里**不构成定位符断言**（那是 M8-T37 自己为 `loop.py` 立的规则），所以这五个键从来没被咨询的机会。**这里学到的判据值得单独记**：豁免键有两种角色——**挡红的**（删掉 `minicc/web_static` → 恰好 2 条红）和**准入的**（删掉 `.minicc/` → 一条红都不产生，只是清单从 782 缩水）。只按"删掉会不会变红"量活性，第二种键永远量不到，所以 `exemption_usage()`（`scripts/doc_pointers.py:826`）量的是"这条键实际答上了几条引用"，命中 0 就是死行。测试里三种情形分开断言：陈旧（没人引用）→ 只有陈旧那条红；被引用但不可达（只写路径前缀、没有文件）→ 只有死行那条红；正常 → 无红。

**门是活的（四条变异，基线 sha256 `405dc6168fb3`，逐条字节还原并复验）**：

| 变异 | 结果 |
| --- | --- |
| A `_top_level()` 改回 `iterdir()` | exit=1，**7 failed / 19 passed**：floors、shipped-docs、端到端、正文第二阅读器，加上本批三条新门全点火 |
| B `_holds()` 退回 `(REPO_ROOT / rel).exists()` | exit=1，1 failed / 25 passed，逐字 `AssertionError: []` + `assert 0 == 1`（"只有本机有的文件，在本机也算红"那条门） |
| C `check-ignore` 恒答否 | exit=1，4 failed / 22 passed，逐字 `DANGLING LINK OPTIMIZATION_DELIVERY_2026-09-18.md:72: 链接目标 ../output/playwright/optimized-1440-light.png 本机有（output/playwright/optimized-1440-light.png），但 git 没有跟踪它，干净检出里这条链接是断的` |
| D 活性循环不跑（`for … in {}.items()`） | exit=1，1 failed / 25 passed，逐字 `assert [] == ['豁免 zzz_noth…则现在挡不到东西，是死行']` |
| 还原后复跑 | exit=0，**26 passed**；`restored byte-exact: True` |

B 与 C 的对照很干净：B 红了说明"未跟踪即红"确有门守着，C 红了说明三态判据里 `generated` 那一格也不是白给的。**A 的锚点是 CRLF 撞出来的教训**：`scripts/doc_pointers.py` 全文 929 行都是 `\r\n`，我按 `\n` 写的多行锚点命中 **0 次**——变异驱动的 `count == 1` 断言第一次不是用来"证明门会红"，而是用来**拒绝一次根本不落地的变异**（M8-T37 那条假绿变异的续集）。驱动因此固定三件事：锚点恰好命中 1 次、写盘前 `compile()`、还原后复验摘要，且匹配在归一化副本上做、写回时恢复文件自己的换行约定。

**当场更正上一批写下的两处断言**：① 「13 条语义已变的引用落在 9 个豁免键上……不是仓库路径（9 键）」——那 9 个键里 **5 个是死行**，真正答上过引用的只有 4 个；② 「当前实测（本批记录定稿时）……811 条 / 17 条」——本批定稿时同一条命令在开发机是 **782 条 / 16 条**（roadmap 570 / README 18，下限 200 / 12 未动），811 那个数不属于任何一份文档，它属于一块磁盘。两处更正都写在原文旁边而不是抹掉，因为"上一批为什么会那样写"本身就是这一批的证据。

**本批最尴尬的一条红，是这段记录自己踩出来的**：写完上面这些字之后跑 `tests/test_doc_pointers.py`，**1 failed**——本批刚写的那条活性门里有一句手抄的 `assert sum(...) == 2`（撤掉 `minicc/web_static` 应产生 2 条红），而这段记录新增了两处对该键的引用，真值变成 4。逐字：`AssertionError: [Problem(... line=676 ...), Proble...里不存在'), Problem(... line=1744 ...)]` / `assert 4 == 2`。**这条红不该用"把 2 改成 4"来消**——那只是把手抄的数换一个继续等下一次改文档的人去撞。改法是把计数与命中计数器对账：`assert len(freed_here) == dp.exemption_usage([_ROADMAP])["minicc/web_static"] >= 1`，并且断言"撤掉这一个键产生的红必须全部属于这个键"（`freed == freed_here`），这样两个数各自都会随文档一起动，而它们**相等**这件事才是判据。这是「数值断言要自带非零守卫」的第二次点火：上一次是 M8-T37 的 `_evidence` 助手抓自己的双计。

**边界（明确不声称）**：**索引 ≠ HEAD**——本批把判据从"磁盘"移到"索引"，而索引包含已 `git add` 未提交的文件，所以那种文件在本地仍然判绿，要到干净检出才红；这条已知残留写进了脚本注释，量它需要 CI 里那一步（见下）。围栏代码块内部与代码片段内部的悬空指针仍然看不见（沿用上一批的口径）。仓库外的路径形状串（`~/.minicc/…`、绝对路径）没有索引可查，仍按存在性判。`_git_output()` 在无 git 环境返回空 → 判据退化为"什么都不跟踪"，本批用 `INVENTORY` 那条门挡成显式红，而不是静默绿。**`--check` 仍未接入 CI**——这条从 M8-T36 拖到现在，接 CI 需要用户批准；而"干净检出 vs 开发机"这组差异之所以能量出来，靠的是我手动 `git worktree add`，一个只有作者会跑的步骤，制度化之前它不算门。

**承重量**：本批新增 4 条门（`tests/test_doc_pointers.py` 22 → 26）、全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1048 passed**（234.05s，exit 0；上一基线 1044，差额恰好等于新增门数 4。改完上面这些字之后同一条命令复跑一次，仍是 **1048 passed** 但 **523.91s**——2.2 倍的差，正好复现 M1-1 那条口径：条数与 exit code 才算口径，wall time 只记"这次跑了多久"）。本批记录主体写完时的实测：`checked 41 pointers (102 spans name no locator), 22 links (2 of them into git-ignored generated output) and 793 evidence pointers (16 path claims sit outside code spans) in 19 documents, over 228 tracked files`——这段记录自己新增了 11 条断言与 4 条交叉引用（上一批定稿是 37 / 95 / 782 / 16），而且写的过程中把本批一条手抄计数判红过一次，见上一条，所以这些数只能定稿时量、不能抄：这一句先前写的是 101，两次补字之后同一条命令读到 102，我没有把这一格差异归因到具体哪一次改动（归因它需要跑两遍并 diff 两份文档，代价高于这条数字本身的价值）——"写下来就会变"就是这类数字的口径。

**提交之后又量了一次（这才是这条退出标准真正想要的形状）**：把刚推上去的 `898aa12` 用 `git worktree add` 检出到别处，那份检出里没有这台机器上的任何生成目录，`--check` 与开发机当时的读数一字不差（41 / 102 / 793 / 16 / 228），并且 `tests/test_doc_pointers.py` 的 **26 条门在那份检出里全绿**（跑的是主仓的解释器，脚本与文档都是检出里的版本）；再往那份检出里种 `output/playwright/` 两张 png、`.minicc/config.json`、`node_modules/`、`.venv/`，总结行**逐字节不变**。上一批只能写"在干净检出里 exit=1"，这一批写的是"干净检出、开发机、种了产物的干净检出三处同一个数"。**同一把尺子立刻又量到我自己**：写完这段之后的定稿读数是 41 / 102 / **795** / 16 / 228——这段"三处同一个数"的证明本身新增了两条证据断言，所以上面那组 793 是它那次运行的数，不是这份文档现在的数。

### 第二十三批 M8-T39：一个整数盖住六件事时，其中一件正在假装通过（2026-09-24）

**起点是总结行里一个不起眼的括号**。上一批之后它长这样：

```
checked 41 pointers (102 spans name no locator), 22 links and 795 evidence pointers …
```

`102 spans name no locator` 是本批要清的那笔账：README 把它写在「明确没管的」一段里，语气是"这块地暂时不覆盖"。可"暂时不覆盖"如果要靠一个整数来交代，那它到底盖住了什么，谁都不知道——包括写下它的人。本批做的第一件事不是改判据，而是**把这 102 条逐条打印出来看**（临时脚本 `t39_boxes.py`，不进仓库）。

**分箱实测**（HEAD 的 19 个文档，143 个「见」标记）：

| 箱 | 条数 | 逐字样本 | 这批给了它什么 |
| --- | --- | --- | --- |
| `checked` | 40 | `见下方「第十三批 M8-T26」` | 原有判据：定位符必须落在存在的标题上，编号必须被**声明**在那一节里 |
| `citation-without-locator` | 15 | `print 口径见下方注记`、`全量数字见上表末格`、`全量基线见本批末尾` | 有名字、有条数、**没有判据**——这是这批明确没解决的那一格 |
| `carried-by-link-reader` | 9 | `完整归属见 [ROADMAP_TO_PRODUCT.md](ROADMAP_TO_PRODUCT.md)` | 目标由链接阅读器解析（三态：跟踪/生成/本机专有） |
| `carried-by-evidence-reader` | 7 | `认证及主题未被回收。指标见 \`…\``（代码片段被掩码后 span 为空） | 掩码吃掉的落点是**另一台阅读器的输入**，不是缺口 |
| `path-in-prose` | 3 | `JUnit 见 output/optimization-final-checks.xml` | 由正文路径阅读器解析（不带豁免时它是红的） |
| `word-interior` | 69 | `零用户可见收益`、`控制台未见错误`、`进度可见性` | **不是指针**，一条都不该计进缺口 |

**最值钱的一条不在这 102 里**。它一直藏在 `checked` 那一栏，而且是绿的：

```
M8-T9 明确不做：可见价值低于 M6–M8 任何一项，排在 M8 之后
```

`见` 后面接的是 `价值低于 M6–M8 任何一项`——一个编号形状的 span。抽取器把它当指针，判据去查 `M6` 与 `M8` 是否声明过，两个都在这个文件里，**通过**。这条不是"没覆盖到"，是**往已核验那一栏记了一笔不存在的东西**：一条假指针比一个未覆盖的缺口糟，因为缺口至少承认自己空着。它就是词内箱里那 69 条的同类，只是恰好后面跟了两个编号。

**判据最后长这样**（两条旧门各教我改了一次，逐字见下表）：

1. span 里带 `第N节 / 第N批 / 附录X` ⇒ **一律算引用**，不管「见」后面粘的是什么。散文不会自己长出一个「第十二节」。
2. span 里只有编号（`M8-T34` 这种）⇒ 必须**站在引用位置上**：以引用词开头（下方/上方/文末/本批/该批/第…/上表/附录）、以 `「` `[` 反引号开头，或以编号本身开头。`可见价值…` 以 `可` 开头 ⇒ 落进词内箱。
3. span 为空 ⇒ 看**未被掩码的原文**：紧跟反引号的是代码片段（证据阅读器的输入），紧跟 `[` 的是链接（链接阅读器的输入），否则就是词内后缀。
4. 每个标记**必须且只能**落进一箱；分箱之和与 `_POINTER` 的独立重数对账，不等就报 `RECONCILE`。

**四次自我推翻，全部由仓库里已有的门拦住**：

| 试过的写法 | 结果 | 学到的 |
| --- | --- | --- |
| 只认「引用词开头」 | `test_appendix_pointers_resolve_by_letter` 红 | `附录` 不在引用词表里，`见附录 B` 掉进词内箱；判据不能照着我脑子里的枚举写，要照门能举出的形状写 |
| 同上（第二条旧门） | `test_cross_document_section_pointer_needs_the_file_named` 红 | `见审核文档第十二节` 的「见」前粘着名词、后面确实有定位符——它是上一批**故意留下当红**的那种真指针，我的新规则差点把它判成散文。**收窄覆盖面的改动会先红在旧门上，前提是旧门里有那一条** |
| 空 span 时看 `match.end()` 之后的原文 | `carried-by-evidence-reader` 从 2 涨到 14 | 掩码保持偏移，但 `match.end()` 已经在被吞掉的代码片段**之后**；要看的是"标记到 span 起点"之间，不是"标记到匹配结尾" |
| 断言 `_GOOD_DOC` 里词内标记 = 6 个 | `assert 1 == 6` 红 | `、` 不终止 span，`可见、意见、预见、见证、见收益` 是**一次**抽取。我把"这个字符出现几次"当成了"这台量具抽到几条" |

**四条变异**（基线 sha256 `41efad1eaf6f`，锚点强制命中 1 次、先 `compile()` 再落盘、跑完字节还原并复验，还原后 `32 passed`）：① 去掉「必须是引用」判据 → `3 failed`（词内标记门、夹具分箱门、分箱下限门）；② `_ID` 退回 `\b` → `2 failed`（引用形状全覆盖门、粘连编号门）；③ 让一箱停止计数 → `13 failed`，其中包括新的 `RECONCILE` 门；④ 总账少印一箱 → `1 failed`（打印出来的账要加得起来）。

**边界（这条没覆盖什么）**：① `_ID` 的 `\b`→ASCII 环视修复，在今天 19 个文档上移动的编号数是 **0**（`old=915 new=915`）——`见下方M8-T26` 这种粘连写法目前只存在于合成门里，所以这条修复**暂时只由合成门撑着**，语料没给它用例；② `citation-without-locator` 那 15 条是真指针，本批只给它箱子与条数，没有判据：能给的最弱形式是「所指的东西要在本文档里出现过」，但 `下方注记`、`上表末格`、`本批末尾` 都不是可 grep 的名字，硬判会把 15 条真指针变成 15 条噪声；③ 阿拉伯数字的 `第8节` 不在 `_SECTION` 的中文数字表里，于是 `证据见交付说明第8节`、`详见总交付第9节` 落进词内箱——它们**是指针而这套量具不查**，且第二条还缺文件名；④ 围栏代码块内部与代码片段内部照旧看不见（`指标见 \`…\`` 那条能落到 evidence 箱，靠的是标记在片段**外面**）；⑤ 一条「见」后面跟两个代码片段（`详细边界见 \`X\` 和 \`Y\``）只计 1 条标记，箱子量标记串不量落点个数。`--check` 接入 CI 仍未由本批决定。

**承重量**：本批新增 6 条门（`tests/test_doc_pointers.py` 26 → 32）、全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1054 passed**（264.74s，exit 0；上一基线 1048，差额恰好等于新增门数 6）。**这段记录本身又是一次"清单会自己长"**：写它之前 `--check` 是 `40 of 143 markers / 795 条证据断言`，写完是 **`42 of 154 / 801`**——本批这段文字新增 11 个标记，其中只有 **2 个**进了 `checked`，其余散进词内箱与 `citation-without-locator` 箱。**复算时踩到一格值得记的**：第一版这里把那个标记字符本身用引号括出来引用了一次，而它自己就是一个标记——于是这句话把它正在抱怨的那个数字从 154 顶到 155，直到改成不引用那个字符才停下来。同一格里还有一处自我演示：我把两条新指针写在反引号里当例子，"反引号里是引用不是断言"那条老规则就把它们掩掉了，所以 `checked` 收到 2 而不是 4。**这类数只能定稿时量、不能抄。**

### 第二十四批 M8-T40：一条判据只认一种写法时，真断言会一直躺在「不是指针」那一箱（2026-09-24）

**起点是上一批自己写下的「做不到」**。第二十三批的边界段里有半句：`见交付说明第8节`、`详见总交付第9节` 落在词内箱，「它确实是指针，只是这台量具查不了」。结案一条挂起项的第一步是**去量它**，不是先改它。

**先量的结果是任务改了方向**。这批原本叫「给 `citation-without-locator` 找判据」。16 条逐条摊开：

| 形状 | 条数 | 逐字样本 | 能不能有判据 |
| --- | --- | --- | --- |
| 指向「注记」 | 4 | `print 口径见下方注记` | 不能——「注记」既不是编号也不是标题号，同一文档里还有多个候选 |
| 指向表格某一格 | 3 | `全量数字见上表末格`、`见下表）` | 不能——落点是坐标，不是任何能被声明的位置 |
| 指向相对位置 | 6 | `全量基线见本批末尾`、`见下一行）`、`见上一条`、`见下面这一行` | 不能——任何「存在即通过」的判据都是自我满足 |
| 指向占位符 | 1 | `见下方第N批` | **不该有**——N 不是数字，判据答它就是在说谎 |
| 其余 | 2 | `见该批记录）`、`见下）` | 同相对位置 |

一箱「有名字、有条数、没有判据」的正确做法，就是上一批已经做的做法：**把条数继续印出来**。所以本批没碰这 16 条；转去量词内箱，**77 条里有 2 条是指针**，而且是真的：`docs/DEEP_OPTIMIZATION_PLAN.md` 第 58、69 行。

**这两条断言本身都是真的，只有量具读不出**。落点在 `docs/OPTIMIZATION_DELIVERY_2026-09-18.md`，它的 level-2 标题自己写着编号（`## 8. 继续实施：第二轮边界收敛`、`## 9. 第三轮剩余行为收尾`）——数字一旦读得出来，就有东西可以答。

**三处改动，缺一处就红**：① `_SECTION`/`_BATCH` 的数字类换成 `_NUM`，两种写法都认；② `_cn_numeral` 改名 `_numeral` 并接受数字（不改名的话，这个名字就在说谎）；③ `_numbered_headings` 从只认 `## 四、` 变成 `^(数字|中文)[.、]`。①② 而没有 ③ 是最坏的组合，M4 变异就是它的机械证明：**读得懂「第8节」却没有任何标题能答它，两条真断言立刻变成两条假红**（5 条门红，含 `test_shipped_documents_have_no_dangling_references`）。

**判据里没变的那一半**：昵称仍然不是可查文件。启用数字之后第一次实跑红的就是这两条——`DANGLING POINTER DEEP_OPTIMIZATION_PLAN.md:58` 与 `:69`，逐字是「指向不存在的第8节」「指向不存在的第9节」。红是对的：「交付说明」在这台工具眼里没有路径可查，而 M8-T36 立下的规矩就是**指针要把文件名写进句子里**。按规矩**改落点、不放宽门**：那两行写成 markdown 链接（link text 保留人读的「交付说明第8节」，target 是 `OPTIMIZATION_DELIVERY_2026-09-18.md`）；同一段前面几行本来就用了这个写法，所以本批只是把同一份信息补齐。工具的读法从「一条无法定位的散文」变成「一次跨文档核对 + 一次链接目标核对」。

**四条变异**（基线 sha256：文档 `0b132c831943`、脚本 `d0e34c21f76a`；每条锚点强制命中 1 次，`.py` 先 `compile()` 再落盘，跑完字节快照还原并复验——还原后的 sha 与动手前一字不差，顺带证明这个文件的原始形态是 CRLF）：

| 变异 | 结果 | 学到什么 |
| --- | --- | --- |
| M1 `第9节` 改成 `第17节` | exit=1，逐字 `指向不存在的第17节` | 编号是被核对的，不是出现过就算 |
| M2 同一编号换文件（`GAP_ANALYSIS_AND_ROADMAP.md` 只有 4 节） | exit=1，`指向不存在的第9节` | 文件名真的被咨询了 |
| M3 撤掉散文侧 `_NUM` 的数字分支 | `3 failed, 35 passed` | 语料门不是只由合成夹具撑着 |
| M4 撤掉标题侧的数字分支 | `5 failed, 33 passed` | 半改比不改更糟 |

**第一次红是红在量具上**：第一版 `mutate()` 走 `read_text`/`write_text` 的文本往返，M1 跑完 `sha256` 复验当场不匹配——磁盘上的文件是 CRLF，文本往返把它写成了 LF。改成**字节快照 + 字节还原**之后四条全部一致，这条记录里所有 sha 都是改完之后重量的。「用来量的工具也要被量」和上一批的「记录会把自己掩码掉」是同一类。

**第二段红是这段记录自己撞出来的**（本批第二条缺陷）。插入第一版 ROADMAP 之后 `--check` 报：`DANGLING LINK ROADMAP_TO_PRODUCT.md:1893: 链接目标 文件 不存在`。原因是我把一个链接形状写进反引号当例子，而**链接阅读器没有掩码这一步**：指针阅读器从 M8-T37 起就把反引号内当引用，`check_links` 却直接在原文上找 `[text](target)`。补 `_LINK.finditer(_mask_code(text))`，代价与指针侧同一条口径一致——只在代码里出现的坏链接这里也看不见。非空守卫量到语料里有 **7** 个链接形状是被引用而不是被声明的，所以这条修改今天就有落点，不是空转。**同时学到的写法**：行内代码对不能跨行掩码，所以这份记录里每个反引号例子都单独占一行的一部分，段落不再硬换行——第一版就是因为硬换行把一个例子劈成两行，掩码失配，才让「记录改变了记录所报的数」。

**顺手把一处静默选择变成被检查的事实**：`_numbered_headings` 遇到两个标题认领同一编号时原来是「后写的赢」，改成 `setdefault`（先写的赢）。这是一个选择不是事实，所以补一条语料门：19 个文档、**57** 个带编号的 level-2 标题，**没有任何编号被认领两次**——平局今天不存在，哪天出现这条门会先红。

**新增 6 条门**：`test_an_arabic_section_number_is_a_locator_and_a_heading_answers_it`（正/负 + 掉箱检查：指针不许落在词内箱）、`test_an_arabic_pointer_to_a_nickname_still_needs_the_file_named`（新定位符继承旧教义）、`test_the_corpus_holds_arabic_pointers_and_the_tool_now_reads_every_one`（语料 2 条全部 `checked`，且没有编号指针留在词内箱）、`test_no_two_level_two_headings_claim_the_same_number`（带非空守卫）、`test_a_link_shape_inside_a_code_span_is_a_quotation`（含未掩码形状仍须红掉的对照）、`test_the_link_reader_actually_has_quotations_to_ignore`（非空守卫）。

**边界（这条没覆盖什么）**：① span 的终止字符集里没有 `）`、`、`、`*`，所以 `见下一行）** 全量 **987 passed**` 这样的句子是一整条 span。今天它没造成任何错误断言：42 条 `checked` 里 14 条带边界字符，其中 **0** 条的编号是在边界字符**之后**才被够到的——但「编号跨过句子边界被够到」正是上一批那条假指针的机制，只是它还需要下文恰好提到一个编号。② `citation-without-locator` 16 条依旧没有判据，本批的表就是它的账本。③ 行内代码掩码不跨物理行，所以写在换行段落中间的反引号例子会露出来被当成断言——这条口径现在由这份记录自己遵守。

**承重量**：本批新增 6 条门（`tests/test_doc_pointers.py` 32 → 38）、全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1060 passed**（exit 0；上一基线 1054，差额恰好等于新增门数 6）。耗时不是内容的函数：同一份改动本批两次全量分别 305.31s 与 197.25s，差在机器负载，所以这里只留「跑过两次」这个事实，不再承诺某个秒数。定稿实测：`checked 46 of 158` 个引用标记（六箱 `checked=46`／`citation-without-locator=16`／`carried-by-link-reader=9`／`carried-by-evidence-reader=7`／`path-in-prose=3`／`word-interior=77`）、23 条链接、813 条证据断言、19 个文档、228 个被跟踪文件，`--check` exit 0。与上一批的差：**两条断言换了箱子，一条也没有新写**。代码改动单独作用在「未插入本批记录的文档」上量到 `checked 42→44 / word-interior 77→75 / 标记 154 不变`；定稿多出的 3 个标记与 2 条 `checked` 是这段记录自己写的引用，指向本批新增的标题，可核对。链接侧补掩码后语料计数 28→23。定稿之后 README 又加了一句解释，句尾的 `看不见` 自己就落进 word-interior 箱（157→158、76→77），checked 与其余四箱不变、分箱之和仍与独立重数相等：这类自计数只在**全仓文本定稿那一刻**稳定，任何一段散文重排都可能动它，所以它承诺的是「当时逐箱对过账」，不承诺逐字复现。**【提交后复验】** 同一条命令在 1d26aa6 的干净检出（`git worktree add --detach` 到临时目录）里读出逐字节相同的总结行，38 条门也在那个工作区通过，所以本批没有「作者本机才成立、干净检出会不一样」的读数。第一次插这段话时它自己把两个数推走了：句尾的 `看得见` 多出一个 word-interior 标记，行内代码里的测试文件名多出一条证据断言——掩码只认反引号，不认新写的散文。

### 第二十五批 M8-T41：一箱承诺「别人会查」，实测七条里五条没人接手（2026-09-24）

**这批不是新写判据，是去兑一张已经开出去的支票。** `carried-by-evidence-reader` 这一箱的名字就是它的断言：这条指针的落点是代码片段，证据阅读器已经在解析它。上一批结案时它记在边界里的那句是「一个「见」跟两个代码片段只计 1 个标记」，听着像最不像问题的一条。先量：**gap 带代码片段的标记全仓总共 7 条**，「两个片段」那种形状 0 条——那条待办本身没有落点，但它把人气味引到了下一层：问这 7 条，它们的片段是不是真的会被那台阅读器接走。**答案是有 2 条会。**

| gap 里的代码片段 | 证据阅读器认吗 | 之前算谁的 | 实际谁都没查什么 |
|---|---|---|---|
| `docs/OPTIMIZATION_DELIVERY_2026-09-18.md` | 认（路径断言） | 证据阅读器 | —— 这一条账是对的 |
| `tests/test_config_surface.py` | 认 | 证据阅读器 | —— 同上 |
| `README.md` | 不认（裸名，无目录） | 证据阅读器 | 这个文件是否存在 |
| `test_anthropic_provider.py` | 不认 | 证据阅读器 | 同上 |
| `config.py:331-338`（两处） | 不认 | 证据阅读器 | 文件是否存在 + 那三十八行是否越界 |
| `output/playwright/frontend-scale-metrics.json` | 不认（头部 `output/` 不在被跟踪集合里） | 证据阅读器 | 该不该按缺失算 |

`_is_path_claim` 拒绝裸名是有道理的：`loop.py`、`scope.js` 这种简写在正文里出现几十次，把它们当路径断言会让证据阅读器一夜之间冒出几百条红。**道理在证据那一侧，不在指针这一侧**——一句「实现细节见 `config.py:331-338`」的落点就是「那个文件的第 331 到 338 行」，这是一条可以答对也可以答错的话，而它当时被记成了「已托管」。

**分箱判据错在哪一行**：那一句问的是「附近有没有反引号」，不是「对方认不认这个形状」。

```python
if "`" in gap:
    return BOX_CODE_SPAN
```

这就是 M8-T39 开的那张账的延续——一箱的含义决定它能不能假装完成，一个可以装下假承诺的箱子比一个明说不管的箱子更糟。

**改法**：交接前验一次发票。`_gap_targets` 给 gap 里每个代码片段定形状，`evidence` 才准进交接箱（语料 7→2）；`name` 进新的第七箱，由指针阅读器自己把它答完：

- 带目录的按链接阅读器同一套存在性问（`_holds`，被跟踪／被忽略／本机有但未跟踪三态）；
- 裸名允许命中**任意**一个被跟踪的同名文件。`config.py:331-338` 说的是位置不是导入路径；硬要求唯一匹配只会教作者把目录名补进去，那是为了哄判据而改文档；
- git 忽略的名字算生成产物，不算缺失；
- 带行号范围的还要答一次「不超过被引文件的行数」（`minicc/config.py` 646 行，331–338 合法）。

**第三条边界，本批按上一批立的规矩写明白**：gap 里确实是代码片段、但既不是证据形状也不像文件名（一个只写着字段名 `answer` 的片段）。它不能留在交接箱（没人查它），也不能落进词内箱——那一箱的含义是「这根本不是引用」，把真引用埋进一个声称自己不是引用的箱子，正是上一批结掉的毛病。所以落 `citation-without-locator`，和 `口径见下方注记` 记同一张明账。**今天的语料在这条规则上移动 0 条**（那 16 条一条没变，全部读数只是把原来交接箱里的 5 条换了名字），所以这条分支目前只由合成门撑着，不假装它已在生产生效。

**账要跟着契约改**：`_pointer_spans` 的返回值从 `(offset, span, box)` 变成 `(offset, span, box, targets)`——因为 `check_pointers` 得知道片段形状才能兑现那条承诺。三条既有门在同一个提交里改账，改完前两次跑是 3 条红（不是 0 红，也不是只有新门红）；分箱从六变七之后，`set(floors) == set(POINTER_BOXES)` 这条旧门逼着下限表也必须加一项——它就是为「只加箱子不改账」准备的。

**五条变异（脚本 sha256 `dbb05e722347`；锚点强制命中 1 次、CRLF 统一后字节快照还原并复验，五条一致）**：

| 变异 | 结果 |
|---|---|
| 分箱退回「gap 里有反引号就算交接」 | `4 failed, 37 passed`：交接箱非空门、名字箱语料落点门、下限门、合成夹具门同时红 |
| 存在性判定给个兜底候选（等于永远查不出缺失） | `1 failed`，红在裸名夹具 |
| 撤掉行号范围判定 | `1 failed`，同一根门（这条说明它和存在性各守一半） |
| 取消「形状得像文件」的要求，任何片段都算名字 | `1 failed`，红在那条 `answer` 门——它保证不会把所有反引号都当断言 |
| 撤掉 gitignore 生成分支 | **`4 failed`**：除夹具外，`test_shipped_documents_have_no_dangling_references` 与端到端门一起红，即那条 `output/…json` 引用会在真实语料上报缺失 |

**承重量**：本批新增 3 条门（`tests/test_doc_pointers.py` 38 → 41）、全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1063 passed**（exit 0；上一基线 1060，差额=新增门数 3）。定稿实测：`checked 48 of 163`，七箱 `checked=48`／`citation-without-locator=16`／`carried-by-link-reader=9`／`carried-by-evidence-reader=2`／`code-span-names-a-file=6`／`path-in-prose=3`／`word-interior=79`，23 条链接、820 条证据断言、19 个文档、228 个被跟踪文件，`--check` exit 0。这份读数里 **5 个标记是这段记录自己写下的**：2 条指向本批标题（落 `checked`）、1 条落进新的名字箱（记录举的那个例子本身就是它，此刻正被同一个文件的行数答过）、2 条是词内后缀（其中一条正是「一个 `见` 跟两个代码片段」那句引文本身——写它的那一秒就把自己的分母改了一次）；证据断言 813→820 同样全部出自本批文本。所以「交接箱 9→2、名字箱 0→6」这两个数里，**只有 6 条中的 1 条来自这段新写的散文**，其余 5 条一直躺在文档里，只是从前算「别人会查」。**交接箱从 9 掉到 2、名字箱从 0 涨到 5，总数一条没变**：本批没有新增任何断言，只是把 5 条已经写在文档里的断言从「别人会查」改成「查过了」。

**下一步还剩什么**（不写成已解决）：`citation-without-locator` 仍是那 16 条有名字没判据的账；行号范围只答了「不越界」，没答「那一行真的是被引内容」——那是另一台阅读器（`::` 测试名门）才有的语义，这里不冒充；裸名匹配接受多个候选，所以 `README.md` 指向 `ide/vscode/README.md` 也不会红，这是「宁要存在、不要唯一」换来的代价，写在这里而不是藏在判据里。

**【提交后复验】** 68317cb 的干净检出（临时 worktree）里同一条命令读出逐字节相同的总结行，41 条门同处通过。这一段刻意不含新的引用标记：写完复测仍是 `48 of 163`——上一批已经教过，解释性散文自己就会改分母。

### 第二十六批 M8-T42：另一个交接箱同样该验发票——这次量出来是干净的，破口在合成形状里（2026-09-24）

**起点与上一批不同**。上一批量出一箱假交接（7 条里 5 条没人接手）；这一批按同一条尺子量另一个箱子 `carried-by-link-reader`，**量出来的结果是它今天全部兑付**：9 条标记，逐条把该标记自己的区域抹掉、再问链接阅读器还剩几条链接可看，计数条条掉落，一条虚报都没有。九个落点逐条列在下表，第三列是链接阅读器对那个目标的判定：

| 文档：行 | 交接目标 | 阅读器判定 |
|---|---|---|
| `AUDIT_2026-09-20.md:509` | `ROADMAP_TO_PRODUCT.md` | tracked |
| `DEEP_OPTIMIZATION_PLAN.md:56` | `OPTIMIZATION_DELIVERY_2026-09-18.md` | tracked |
| `OPTIMIZATION_DELIVERY_2026-09-18.md:27` | `BACKEND_OPTIMIZATION_DELIVERY.md` | tracked |
| `OPTIMIZATION_DELIVERY_2026-09-18.md:148` | `BENCHMARK_EVALUATION.md` | tracked |
| `OPTIMIZATION_DELIVERY_2026-09-18.md:158` | `FRONTEND_HARDENING_DELIVERY.md` | tracked |
| `OPTIMIZATION_DELIVERY_2026-09-18.md:174` | `SNAPSHOT_COMPLETION_HARDENING.md` | tracked |
| `README.md:257` | `docs/SPECPROOF_ASSESSMENT.md` | tracked |
| `README.md:261` | `docs/AGENT_RESEARCH.md` | tracked |
| `README.md:299` | 两条：`docs/DEEP_OPTIMIZATION_PLAN.md`、`docs/OPTIMIZATION_DELIVERY_2026-09-18.md` | tracked |

**这不足以判它没问题**——九条都是同一种形状（`见 [文字](目标)`，方括号紧贴在标记后面），语料只教了判据的一种情形。用合成句子探边界，判据立刻两头都错：

| 合成句子（去掉外层反引号即是原文） | 分箱给出的承诺 | `check_links` 实报的 `checked` |
|---|---|---|
| 一个方括号，根本不是链接：`[待定]` | 已托管 | 0 |
| 页内锚点：`[本节](#t)` | 已托管 | 0 |
| 外链：`[官网](https://example.com/x)` | 已托管 | 0 |
| 空目标：`[说明]()` | 已托管 | 0 |
| 目标里带空格：`[说明](a b.md)` | 已托管 | 0 |
| 方括号不在 span 首位的真链接：`见下方 [说明](README.md) 一条` | **没判据**（那格明写着「本工具查不了」） | 1 |

前五行的意思是：一台阅读器说「这不是我的事」（它的语法不收这些形状），另一台说「别人会查」（分箱收了这些形状）——一条断言就在两台互相推诿中记成了已核验。最后一行是同一个洞的另一面：一个**一秒可核**的目标被写进了那格「有名字、有条数、没有判据」的明账，等于把可查的东西谎报成不可查。**两个方向的错在总数上互相抵消**，所以这条洞在语料里活到今天。

**改法：判据换成对方自己的语法，两张跳过表合成一份。**

```
旧：if "[" in gap or span.startswith("["):     # 只问有没有方括号
        return BOX_LINK_TEXT
新：if _region_has_judged_link(region):        # region = 掩码后的标记自身区域
        return BOX_LINK_TEXT
    if "[" in gap or span.startswith("["):     # 有括号但对方不判 → 不许白拿托管
        return BOX_NO_LOCATOR if cited else BOX_WORD
```

`_link_judged` 是那条跳过表的**唯一副本**：链接阅读器判不判一个目标要走它，指针侧要不要托管一个标记也要走它。上一批的教训是「两台阅读器各持一份规则就会漂移」，这次不是加一条门去盯漂移，而是让漂移无处发生。区域取**掩码后**的文本，于是「只在反引号里出现的链接」在两台阅读器里一致地不判（M8-T40 的那条口径第一次真正传到指针侧）。

**四条变异（脚本 sha256 `1a74a5f09524`；锚点强制命中、字节快照还原复验，四条一致）**：

| 变异 | 结果 |
|---|---|
| 退回「有方括号就算托管」 | `3 failed`：五个形状门、反向那条真链接、以及 M8-T40 的反引号门 |
| 交接箱永远不受理 | `5 failed`：除上述两条外，还有下限门与语料对账门——9 条交接一夜清零会被当场抓住 |
| 放宽跳过表（外链也算） | `5 failed`，其中 `test_relative_links_must_resolve_and_urls_are_left_alone`、`test_shipped_documents_have_no_dangling_references` 与端到端门都是**本批之前就有的门**：这条规则不是新门独撑 |
| 区域换成未掩码文本 | `1 failed`，红在那条「反引号里的链接形状是引用不是断言」的老门（本批给它补了两条指针侧断言，就是本小节末尾围栏里的两条） |

**语料影响：两侧各移动 0 条。** `carried-by-link-reader` 仍是 9、`citation-without-locator` 仍是 16、总结行仍是 `checked 48 of 163`——本批改的是判据的强度，不是文档的错误。所以这一类的守护今天**只由合成门撑着**，照 M8-T40 那条「语料移动 0，门是唯一的墙」的规矩写在这里。为了让它不是一句自我表扬，第三条新门做成语料级的对账而不是合成夹具：每个落进交接箱的标记，都把它自己的区域抹掉后**重新问一遍链接阅读器**，计数不掉即红——判据读的是 `check_links` 的返回值，不是指针侧对同一条规则的第二份拷贝。

**顺带修好的一条老门**：M8-T40 的「反引号里的链接形状是引用」那条门从前只断言链接阅读器，本批给它加上指针侧的孪生断言——同一条句子带反引号不得落交接箱、去掉反引号必须落交接箱。两条形状写在下面的围栏里（围栏内容对三台阅读器都是引用，不是断言；把它们抄进散文的代价本批实测到一次：那条链接形状会自己变成一条新断言，进链接阅读器的账）：

```markdown
结论见「说明 `[README](README.md)` 那段」。    # 掩码护住 → 不落交接箱（落 word-interior）
结论见「说明 [README](README.md) 那段」。      # 真链接   → 落交接箱
```

**边界照写**：那条落 `word-interior` 而不是 `citation-without-locator`，是因为它的 span 不以引用位置开头——`cited` 规则是 M8-T39 定稿的，本批不动它，但它意味着「掩码挡住了假交接」这件事的落点仍不是最贴切的那一格。

**下一步还剩什么**（不写成已解决）。① 交接箱问的是「这个区域里有没有一条对方会判的链接」，不是「这个标记指的就是那条链接」——一个同时点了两样东西的标记只会被链接那半答到，名字那半不再做行号对账。四种连写形状实测如下（前三条今天就已经是这个落点，本批没改它）：

```markdown
口径见下方表格，另参 [README](README.md)。        # 仍是「没判据」——逗号截断了 span
口径见 README.md 与 [说明](nope_missing_file.md)。  # 落交接箱：链接被答，裸名那半没被行号对账
详见 [说明](README.md) 那一段，口径同上。           # 落交接箱
参见 [说明](README.md) 与下方表格。                 # 落交接箱：「下方表格」那半没人答
```

② `citation-without-locator` 仍是那 16 条有名字没判据的账；③ 掩码护住的那条形如「引号里再套反引号」的标记落 `word-interior` 而不是 `citation-without-locator`，落点仍不贴切（本批按 M8-T39 的 `cited` 规则原样保留）；④ 一个只在代码片段里出现的坏链接，两台阅读器今天都不判它——这是掩码的既定代价，不是本批新增的洞。

**承重量**：新增 3 条门（`tests/test_doc_pointers.py` 41 → 44），全量 `.venv/Scripts/python.exe -m pytest -q -W error` **1066 passed**（exit 0；上一基线 1063，差额=新增门数 3；用时两次实测 233.62s／397.17s，与内容无关，只作记录）。定稿实测：`checked 50 of 166`，七箱 `checked=50`／`citation-without-locator=16`／`carried-by-link-reader=9`／`carried-by-evidence-reader=2`／`code-span-names-a-file=6`／`path-in-prose=3`／`word-interior=80`，23 条链接、828 条证据断言、19 个文档、228 个被跟踪文件，`--check` exit 0。**这份读数里 3 个标记是这段记录自己写下的**（表格行 126→129）：2 条指向本批新章节的标题（落 `checked`，两侧编号都在标题里声明过），1 条是表格行里 `看不见` 那个后缀（落 `word-interior`）；证据断言 820→828 的 8 条全部出自本批那张九行落点表——每一条形如 `文档.md:行号` 的引用都被被引文件的真实行数答过一遍，这也是它们进账而非进红的原因。**所以本批那句「两侧各移动 0 条」要这样读**：把这段记录撤掉，语料读数回到 `48 of 163` 且七箱逐格相同；`carried-by-link-reader` 从头到尾是 9，`citation-without-locator` 从头到尾是 16。

**【提交后复验】** fe53f3c 的干净检出（临时 worktree）里同一条命令读出逐字节相同的总结行，44 条门同处通过。这一段刻意不含新的引用标记：写完复测仍是 `50 of 166`，七箱逐格相同——上一批已经教过一次，解释性散文自己就会改分子。


### 第二十七批 M8-T43：引号命名的指针今天没人读——而先量的结果本身是第二条发现（2026-09-25）

**起点是上一批留下的那句话。** M8-T42 说「两张跳过表合成一份，漂移就无处发生」。仓库里还有第三对同一想法的
两份拷贝：抽取器 `_POINTER` 的方位词组认十个词（下方、上方、文末、上一段、下一段、上一行、下一行、本节、
本批末尾、该批），判据 `_CITATION_HEAD` 认十七个。差别不是抽象的：本文档里有一条写作 `见下文「当前实测」段` 的
指针，「下文」只在长的那份表里，于是它**从来没走过引号分支**——名字和方位词一起被塞进一个原始 span，
没有任何阅读器被问过这件事。

**量这件事本身暴露了第二层问题。** 用十七个词那一侧重跑抽取：语料里有 24 条形如 `见…「X」` 的引号命名指针，
其中 23 条的名字带编号（`第8节`、`M8-T34`、`第二十六批`），今天已被定位符阅读器答掉；恰好 1 条既不带编号也没人读。
**所以两份表漂移的代价不是「少判一条」，是「少了几条量不出来」**：短表让这一形状在语料里的表现是 0，
任何「语料里有没有这类东西」的探针对它只能报 0——这比上一批「语料 9 条全部兑付」更糟，那种情况下至少还看得见样本。

**只做语法合并会立刻造成一个反向的错。** 把抽取器的方位词组换成长表，本批那套门跑一遍：那条标记从
`citation-without-locator`（有名字、有条数、没有判据）搬进了 `word-interior`——而 M8-T40 已经确立那一格的含义是
**「根本不是引用」**。一条真实断言被改判成「这不是指针」，比没人读更糟：它从此连「我没被查」这条明账都不挂了。
抓得到、有专属格子、有阅读器答它，必须同批落地。

**改法：第八箱 + 本阅读器自己答。**

| 件 | 内容 |
|---|---|
| 一份方位词表 | `_DIRECTION` 是唯一来源，抽取、head 判据、`_PLACE_WORD`、`_AFTER_MARKER` 四处都从它拼接 |
| 收窄的受理条件 | 只有 `见<方位词>「X」` 算处所引用；裸 `见「X」` 仍由 M8-T39 的 head 判据决定 |
| 新箱 `cites-a-quoted-name` | 有名字、有阅读器，不再是明账；刻意**不进** `checked` 那个整数，让它继续只表示「定位符形状的目标被解析掉了」 |
| 声明的三种写法 | 标题文本、`**粗体标签**`、表格行首格；名字必须落在指针声称的那一侧 |
| 方向 | `上*`（上文/上表/上一行/上方）要在前，`下*` 要在后，`本节`/`本批`/`该批`/`文末`（以及无方位词）只要求本文档里有 |
| 自引守卫 | _extent_ 覆盖指针自身的那条标签不算声明 |

**量出来的第二条真实缺陷：该修的是文档，不是判据。** 那条指针命名的 `当前实测` 在本文档里从未被**声明**过，
它只是散文里顺口用的词。按 M8-T36 定下的口径（编号要被声明在标题或行标签里，只在正文出现过不算），
本批把那一处标签写成粗体，而不是把判据放宽成「正文里出现过就算」。

**收窄不是可选项：一个反例形状。** 如果凡是引号里的 span 都算处所引用，M8-T40 那条「反引号里的链接形状是引用
不是断言」的老门就要改判——它写的正是 `见「说明 …那段」` 这种**描述**而非**处所**。四条形状写在下面的围栏里
（围栏内容对三台阅读器都是引用，不是断言）：

```markdown
口径见下文「当前实测」一段。         # 方位词＋引号 → cites-a-quoted-name，本阅读器答
结论见「基线」这里。                 # 只有引号 → 仍由 head 判据决定（落词内箱）
口径见 `x` 「当前实测」。            # 掩码改变 gap → 不算处所引用
见下文「第8节」。                    # 带定位符 → 先走 checked，两箱不重复计
```

**五条变异（脚本 sha256 `8331bf727484`；锚点强制命中 1 次、字节快照还原复验，五条一致）**：

| 变异 | 结果 |
|---|---|
| 只合并抽取、新箱永不受理 | `5 failed`：箱下限门、本批三条判据门、语料对账门——抓进来却无人答的标记一夜落进词内箱 |
| 去掉自引守卫 | `1 failed`，红在「指针把自己的句子包成粗体标签」那条门：这条守卫只有它撑着 |
| 放宽成「凡引号皆处所」 | `2 failed`：本批的收窄门 **以及 M8-T40 的老掩码门**——这条规则不是新门独撑 |
| 两份方位词表重新分叉 | `4 failed`（下限门、方向门、词表门、语料门），即本批起点的那个状态 |
| 量词里多一个空格（`{1, 60}`） | `7 failed`，其中最值钱的是下限门那句「harvest 到 0 条，低于下限 15」 |

**语料影响：`citation-without-locator` 16 → 15、`cites-a-quoted-name` 0 → 1、`checked` 仍是 50。** 新箱不进
`checked` 那个整数，所以总结行的分子分母都没动，移动只发生在分箱之间——这一句要这样读：本批既没有新核验任何
一条定位符，也没有让任何一条断言变得无人认领。

**本批自己踩的坑，值得单独进门。** 新写的 docstring 里有一个转义的反引号，那是 `invalid escape sequence`；
但它只在**源码被重新编译**时才会作为 DeprecationWarning 冒出来，而磁盘上的旧字节码（`__pycache__`）比源文件新，
于是 `-W error` 的全量套件白绿了几个小时。暴露它的是本批的变异脚本：重写源文件让缓存失效，第一条命令就撞成
collection error。**「测试跑过了」不等于「测试被编译过」**——一条只靠缓存的门，其结论的成立条件是「上一台机器
什么时候写过这个文件」。改法两半：去掉那对反斜杠，并新增一条门，把磁盘上的字节重新 `compile()` 一遍、
warnings 升级为 error。这条门与分箱无关，纯守「源码被重新读一次会怎样」。

**承重量**：新增 6 条门（`tests/test_doc_pointers.py` 44 → 50，5 条判据门 + 1 条编译门），全量
`.venv/Scripts/python.exe -m pytest -q -W error` **1072 passed**（exit 0；上一基线 1066，差额=新增门数；
用时两次实测 464.96s／489.27s，后者是这段记录写完之后重跑的，与内容无关只作记录——M8-T40 已确立耗时不是内容的函数）。

**定稿读数（这段记录自己贡献的 2 个标记已经算在里面）**：`checked 51 of 168`，八箱 `checked=51`／`citation-without-locator=15`／`carried-by-link-reader=9`／`carried-by-evidence-reader=2`／`code-span-names-a-file=6`／`cites-a-quoted-name=1`／`path-in-prose=3`／`word-interior=81`。其中 2 个是这段记录写下的：表格行那 1 条落 `checked`（编号两侧都声明在本批标题里），1 条落 `word-interior`（散文里那个 `看得见` 是后缀不是引用，M8-T39 的规则）。把表格行与这一整节都撤掉，读数回到 `checked 50 of 166`，而 `citation-without-locator=15`、`cites-a-quoted-name=1` 保持不变——**本批对语料的净效果就是那一条移动**：一条真实的处所引用从「有名字没判据」的明账，进到有人答它的格子里。

**边界照写**（不写成已解决）。① 名字是**子串**匹配不是全等——判据弱，但至少可核，且不会因为改几个字就变红；
② 方位词只排**声明位置**的前后，不读被引段落的语义，`见下文` 配一个毫不相干的同名标题今天算通过；
③ 引号里带定位符的仍由定位符阅读器先答，两箱不重复计；④ 一条指针同时点两样东西（引号名字 + 链接）仍只答一半，
这是 M8-T42 边界①的同一件事；⑤ `citation-without-locator` 仍剩 15 条有名字没判据的账；⑥ 抽取 widening 之后，
`见下「X」` 这种单字方位词也算处所引用——它扩大了受理面，本批没有语料样本，属于只由合成门撑着的一类。


**【提交后复验】** 50dff6f 的干净检出（临时 worktree，那里没有任何 `__pycache__`）里：同一条命令读出逐字节相同的 `checked 51 of 168`，八箱逐格相同，50 条门同处通过。这一次复验不是仪式——本批新增的那条「从磁盘字节重新编译」的门，它的红法就是「只有冷缓存才会报」：这类缺陷在热缓存里永远绿，所以「跑过了」在开发机上根本不等于「被编译过」，只有在干净检出里跑一次才算验证。这一段刻意不含新的处所引用（写完复测仍是 `51 of 168`，八箱逐格相同）——上一批已经教过一次，解释性散文自己就会改分子。

### 第二十八批 M8-T44：一条指针可以同时点两样东西，而第二样没人答（2026-09-25）

**起点**是上一批留下的边界④：「一条指针同时点两样东西仍只答一半」。这一批不再猜那一半是什么，去量它。

**先量，量法自己错了三次；改完之后做归因，又错了一次**：

| 量法 | 读数 | 为什么不算数 |
| --- | --- | --- |
| 标记后面 200 字的窗口 | 交接箱 9 条里「4 条同时点名了别的东西」 | 窗口会读进同一行**别的**代码片段，4 条全是假租户 |
| 收窄到标记自己 harvest 的 `span` | 八个箱子全部 0 条 | 0 要先证明量具看得见：同一条抽取管线喂 9 条合成样本，`span` 里的裸名照样被抓到（`names-in-span=['nope.md']`）——所以这个 0 是真的 |
| 只调 `check_pointers` 判「有没有人答」 | 「点名不存在的文档」被判成假绿 | 整件工具还有散文路径阅读器，它只认带目录的名字（`_prose_path_claims` 里那句 `if "/" in claim`）。这条红其实是 PROSE 报的 |
| 归因时用 (span, 箱) 的**集合**差 | 「这段记录自己贡献 3 个标记」只报出 2 条 | 本批复用了文档里已有的拼法：重复的标记进分母却不进集合。换成**重数**（Counter）差才与语料读数的 +4 对得上——同一个数被两种量法读出两个结果时必须当场对账，不能挑一个顺眼的写进记录 |

改用出货入口 `check_document` 之后仍然出过一次鬼：六个用例覆写同一个探针文件，其中一例报出一条**行号为 1** 的节红，而单独复跑同一条是绿的。覆写窗口不可信，改成**一例一个新文件**后读数才稳定。这条不是形式主义——同一份内容在两次读取里给出不同答案，任何一条结论都不该建立在它之上。

**稳定读数（改前，五例两控制组）**：

| 例 | 文本 | 改前读数 | 该当如何 |
| --- | --- | --- | --- |
| `B` | `结论见 README.md 第8节`（README.md 没有任何编号二级标题） | `problems=NONE`、`checked=1` | 红：它说的是另一个文件 |
| `C` 控制组 | `结论见第8节`（节真的在本文） | `problems=NONE`、`checked=1` | 绿。**B 与 C 逐字段相同** ⇒ 落点根本不是它点名的文件，而账上分辨不出来 |
| `A` | 点名一个不存在的文档 + 本文恰好有该节 | PROSE 报「路径不存在」，`checked` 仍 +1 | 文件在不在由 PROSE 答；那一节归谁，指针栏自己答 |
| `D` | `口径见 nope.md 与 [说明](README.md)` | `NONE` | 裸名不是链接阅读器的事，也不是证据阅读器的事 |
| `F` | `口径见 nope.md`（无定位符） | 落进 `word-interior` | 那一格的含义是「这里根本没发生引用」——真断言躺在否认可存在的格子里 |
| `C2` 控制组 | `结论见 docs/PLUGIN_API.md 第3节`（该文档真有第3节） | `problems=NONE`、`checked=1` | 改前改后都该绿；它保证新判据不是「凡点名文档就红」 |

**改法**：

| 一处 | 做法 | 为什么这样 |
| --- | --- | --- |
| 所有权 | 标记自己的 span 点了 `.md` 文档，`第N节` **只在该文档里解析**；查不到就红，并说出是哪本文件 | 回退到本文同名节，等于回答另一个问题。`_numbered_sections` 复用 `_numbered_headings`——「什么算拥有第N节」只能有一处定义 |
| 裸名归位 | span 里的裸文件名交给 M8-T41 的名字判据（`_check_name_targets`），交接箱与 `citation-without-locator` 一并受理 | 那两格的原话是「别人会查」；`nope.md` 没有任何别人。复用现成判据而不是再写一套：裸名允许命中任意同名文件、被忽略的算生成产物、行号不得越界 |
| 不双计 | **带目录的名字交给散文阅读器，指针侧刻意不重报**；链接自己的目标同样剔除 | 一票两处开票就是 M8-T41 反对的那种账。指针这一栏的补集正好由对方那句 `if "/" in claim` 定义——不是随手挑的名单 |
| 单一来源 | 裸文件名的形状由 `_PROSE_PATH` 拼进引用头，不另抄一份扩展名清单 | 上一批刚数过同一想法的第三对漂移；手抄副本行为可以完全等价，而两份表总有一天会不同意 |

**语料影响：规则改动移动 0 条——这句话由反事实撑着，不是由两句读数相减撑着。** 定稿读数 `checked 53 of 172`（`checked=53`、`citation-without-locator=15`、`carried-by-link-reader=9`、`carried-by-evidence-reader=2`、`code-span-names-a-file=6`、`cites-a-quoted-name=1`、`path-in-prose=3`、`word-interior=83`），`--check` exit 0，证据指针从 829 涨到 830（本批那条测试名指针进了账）。但它比上一批定稿的 `51 of 168` 多出 2 个分子、4 个分母：这 4 个标记是这段记录自己写下的（本批的表格行与整节里，2 条处所引用进 `checked`——一条指向本节，一条指向本批末尾那条候选标题；2 条词内标记进 `word-interior`）。所以「移动 0 条」不能拿这两句话相减来验——那等于把作者自己的散文记在规则改动的账上。反事实的测法：把本批的表格行与整节删掉，**仍走出货入口 `check_document`** 逐文档重测全仓，读数逐格回到 `51/168`、八箱 `[51,15,9,2,6,1,3,81]`、`red=0`、证据指针仍是 829（写前先快照、`finally` 里还原并复验字节一致，因为被改动的正是未提交的工作）。**这段记录自己造过一条红**：那第 2 条处所引用最初指向一个还不存在的批号，阅读器的原话是「说 M8-T45 在本文档里，那里没有这个编号」，`--check` 当场非零。按 M8-T36/T40 的口径改落点（把候选声明成一条带编号的标题）而不是放宽门；改完 exit 0。同一批里还把这段候选插错了位置：锚点命中的是**上一批**那一节——`assert count == 1` 只保证这句话在全仓落一次，它不保证那一次在**我这一批**里（本批那行边界写作的是「边界照写：」，带冒号不带括号）。是 `grep -n` 复读落点才看出行号落在上一批的小节里。**唯一命中不等于命中对的地方。**归因那一步的量法也错过一次：(span, 箱) 的集合差只报 2 条，重数差才报出全部，记在上面那张表里。这一批的重量全部落在合成门与控制组上——「类可达、租户为 0」是先量量出来的事实，不是推测。上一批同样 0 移动，那次的经验（记录要写清「只由合成门撑着」，也要写清解释性散文自己会改分子）在这里继续适用。

**六条新门（50 → 56）**，其中三条是成对的控制组（B/C、D/D2、`C2`），因为「红了一次」不证明判据认得正确答案。全量套件在本批量到三个读数，其中两个不是绿色，先按事实写下来：记录落地之前那次是 **1078 passed**（546.86s，冷字节码；上一批那条「从磁盘字节重新 compile()」的门这次就在承重——变异脚本每次重写源文件）；记录落地之后连着两次全量都是 **1 failed、1077 passed**（984.72s 与 1134.36s），红的都是 `tests/test_retrieval_enhanced.py::test_thousand_file_index_builds_within_budget` 这条计时门（elapsed 10.06s 对上限 8.0s），而本批一个字没有碰检索代码。同一份形状在几分钟内单独连跑三次量到 **3.06s、19.90s、45.05s**（Temp 里的一次性探针，不进仓库），同一条门单独跑又绿——所以这条上限今天量的是**机器负载**，不是代码（此刻机上还有若干并行会话与 esbuild watch 进程在打磁盘）。结论按 M8-T40 的口径写：一次红不能记成产品回归，一次绿也不能记成产品健康；计时类门要改成「同一次运行内的相对判据」（例如 1000 文件与 250 文件的比值上限），这样上限才不是外部负载的函数——已挂成下一批候选，见下方「M8-T45 候选」一节。

**五条变异**（运行器 sha256 前缀 `04e4241dc54e`；锚点强制命中一次、还原后复验字节一致，跑前基线 56 passed 绿）：

| 变异 | 红在 |
| --- | --- |
| m1 去掉所有权规则（回到先看本文） | 2 条：B/C 那条 + 「报错要说出被怪的文档」那条 |
| m2 交接箱与无定位符箱不再回答裸名 | 2 条：`D` 那条 + `F` 那条 |
| m3 裸名规则不再排除带目录的名字 | 1 条：一票两处那条 |
| m4 把形状手抄一份进引用头（`.pattern` 逐字相同、行为等价） | 1 条：唯一副本那条门——**它红不了任何行为门，这正是它存在的理由** |
| m5 裸名不再算引用头（`F` 回到 `word-interior`） | 2 条：`F` 那条 + 唯一副本那条 |

m4 第一轮是**零证据变异**：heredoc 把 `\b` 吃成退格符，引用头再也匹配不上任何裸名，两条行为门一起红——红的是变异自己，不是被检查的代码。补上「变异文本必须原样落进文件、且不含控制字符」的自检后重跑，才得到上面那一行。**这条自检与 M8-T37 的「锚点须命中一次、还原须复验 sha256」是同一类东西：变异脚本自己没有落盘证明，它的红就没有意义。**

#### M8-T45 候选（下一批）：计时门的上限不该是机器负载的函数

判据形状：同一次运行里跑两种规模（例如 1000 文件与 250 文件），断言**比值**有上限而不是断言秒数有上限——比值对负载不敏感，绝对秒数敏感。本批只留下证据（3.06s、19.90s、45.05s 三个数来自同一份形状），不动那条门：把计时门改成相对判据需要自己的对照实验，塞进一批文档改动里会让两件事都失去可核性。


**（结案：本候选由下方「第二十九批 M8-T45」处理，但结论与这里写的处方不同——比值也量的是负载，承重的判据换成了每文件系统调用次数。原文一字未改，因为它记的是当时量到的三个读数，那三个数是真的。）**

**边界照写**：① 所有权规则只覆盖 `第N节`；`第N批` 仍只在本文声明，跨文件的批号记录走 M8-T40 那条「句中点名文档」的通路，本批没动它。② 裸名判据只在**标记自己的 span** 里生效；同一句另一处的裸名不在任何一栏的账上（那正是 200 字窗口造的假租户形状）。③ `A` 组现在两条红各答一条断言（文件在不在 / 那一节归谁）——若哪天散文阅读器的斜杠判据改了，这条分工要重新量。④ 带目录的名字交给散文阅读器，代价是指针栏里那条 `checked=1` 仍会说「这一条已解析」，而它点名的文件根本不存在：`checked` 那个整数的含义是「定位符形状的目标被解析掉了」，本批没有把它扩大。⑤ `cites-a-quoted-name` 那一格仍不受理 span 里的裸名（引号内是描述，M8-T43 的口径）。⑥ `_numbered_sections` 按 `Path` 记忆化：同一次进程里外部改动那本文件不会被重读，跨 worktree/改名不会串。⑦ 本批没有把那条计时门改成相对判据，只留下三个读数与「上限是负载的函数」这条证据——改它需要单独一次对照实验（同一进程内两种规模各跑一次），不该塞进一批文档改动里。

**【提交后复验】** `8f318ea` 的干净检出（临时 worktree，那里没有任何 `__pycache__`）里：同一条命令读出逐字节相同的 `checked 53 of 172`、八箱逐格相同、830 个证据指针、228 个受版本控制的文件，`--check` exit 0；56 条门在同一份冷字节码上全部通过，用时 28.34s。这一次复验对本批有具体内容而不是仪式：阅读器与它自己的记录分在**两个提交**里，而记录引用的是「出货的那份阅读器」的读数——只有从 HEAD 重新检出、重新编译，才知道那串数字不是本机某份未提交的运行器算出来的。本批那条反事实也在 HEAD 的正文上重算了一遍：同一份文件删掉表格行与整节后从 `48 of 135` 回到 `46 of 131`、无红，差值仍是「2 条处所引用加 2 条词内标记」，所以「规则改动移动 0 条」这句结论同样不依赖工作区。反过来，记录里唯一一组不指望在这里复现的数字是全量套件的耗时与那条计时门的三次读数——它被写成机器负载的函数而不是内容的函数，这正是 M8-T45 的选题理由。这一段刻意不含处所引用与裸文件名（写完复测仍是 `53 of 172`，八箱逐格相同）：解释性散文自己就会改分子，这件事上一批已经付过一次账。

### 第二十九批 M8-T45：一条计时门量的是机器负载，换成一把不看秒数的尺子（2026-09-25）

**先量，量出来的第一条是上一批自己的处方不成立。** 起点在上一批末尾那条候选里：1000 文件的构建门上限写着 8.0s，连着两次在全量套件里红在 10.06s，而那批一个字没碰检索代码；同一份形状单独连跑三次量到 3.06s、19.90s、45.05s。候选写的改法是「同一次运行内跑两种规模，断言**比值**有上限」，理由是「比值对负载不敏感」。**这句话本批实测为假**：

| 条件 | 250 文件 | 1000 文件 | wall 比值 | 每文件调用比值 | 每文件 CPU 比值 |
| --- | --- | --- | --- | --- | --- |
| 正常（代码未动）run0 | 0.74s | 3.41s | 4.64 | 0.9954 | 1.05 |
| 正常（代码未动）run1 | 0.99s | 4.42s | 4.46 | 0.9954 | 0.86 |
| 挂上纯 CPU 二次扫描 run0 | 1.27s | 5.09s | 4.01 | 0.9954 | 1.23 |
| 挂上纯 CPU 二次扫描 run1 | 0.82s | 3.28s | 4.02 | 0.9954 | 0.99 |
| 撤掉变异（对照）run0 | 1.91s | 3.98s | 2.09 | 0.9954 | 1.00 |
| 撤掉变异（对照）run1 | 0.94s | 4.29s | 4.54 | 0.9954 | 1.01 |

未改代码的 wall 比值在 2.09~4.64 之间摆，一次货真价实的 `O(n^2 log N)` 回归读到 4.01~4.02——**变异区间完全落在对照抖动之内**。按比值设上限只有两种下场：上限大于 4.64 就永远抓不到东西，小于则本批第一轮就会红。每文件 `process_time` 比值同样重叠（对照 0.86~1.05、变异 0.99~1.23），也不是那把尺子。唯一在这六行读数里逐字节不动的量是**每文件文件系统调用次数**：小形状 5.232、大形状 5.208、比值 0.9954，上面那六行（三种条件 × 两轮）一个都不差。所以判据搬到这里来。

**新门的形状：一把仪器、两根判据、三个见证。** 仪器是 `_count_filesystem_calls`——包 `Path.stat`、`Path.open`、`Path.is_symlink`、`Path.iterdir` 与 `os.walk` 这五个符号，跑完在 `finally` 里还原并复验 `Path.stat` 还是原函数（Python 3.11 在 import 时就把 `os.stat` 绑进 pathlib 的 accessor，包 `os` 模块会静默漏掉每一次 `Path.stat()`，仪器会坏成恒 0 而全场没人知道）。判据两根：每文件常数的**上限**（≤ 7.0）抓「每个文件多做了几件事」，两规模的**比值**（≤ 1.25）抓「做的事随文件数增长」——m2 那一行就是各管一头的实测。另有两条把「只走一次树、每份正文只读一次」钉成恒等式：`open == files_indexed`、`walk == 1`。

五新（`tests/test_retrieval_enhanced.py` 15 → 20）：`test_index_build_makes_a_constant_number_of_filesystem_calls_per_file`（两根判据）、`test_the_call_counter_is_the_same_number_on_every_rebuild`（同树重建两次读数全等，另加 `sum > 250` 的非空守卫——计数器累加了两次而不是每轮归零）、`test_the_counter_can_see_quadratic_growth`（20/50 文件上的合成二次扫描与线性对照组，线性一侧 `== 1.0`、二次一侧增长 `> 2.0`）、`test_searching_a_built_index_touches_no_disk`（20 次查询共 0 次调用，且**结果非空**：缺席类门必须同时证明窗口里真发生了事）、`test_refreshing_an_unchanged_tree_reopens_no_file_body`（`open == 0` 而 `walk == 1`、`stat >= 250`——精确说出免费的是哪一半，签名复用不免费走树）。

**「0 要先证明量具看得见」在这里有一个新含义**：这条门能看见系统调用的增长（上面那条见证就是它自己喂的），但**看不见纯 CPU 的增长**——表里那两行「挂上纯 CPU 二次扫描」的调用比值仍是 0.9954，一次不差。这不是漏，是这把尺子的定义域，写在两处 docstring 里而不是藏在成功叙事里：一条构建如果只慢在算得不慢在读，今天仓库里没有任何门会红。要覆盖它需要另一个结构量（例如索引器自己数它对记录做了多少次全表遍历），本批没做，见下方「M8-T48 候选」。

**五条变异**（脚本自证：锚点强制命中 1 次、新文本原样落盘、还原后与基线 sha256 逐字节相同；运行器 sha256 `1d33af2eada9`）：

| 变异 | 红法 |
| --- | --- |
| m1 计数器不再累加（仪器坏成恒 0） | 四条红、**一条绿**：红在常数上限、同数复验、二次见证与「刷新不重读正文」（那里 `walk == 1` 的恒等式也一起红），绿的正是那条「查盘 0 次」的缺席门——它看到 0 == 0 就满意了。缺席类门看不见仪器失效，本仓由 `open == files_indexed` 与那条非空守卫代它承重 |
| m2 每个文件多 stat 五次（常数膨胀，不是二次） | 一条红在 `assert 10.208 <= 7.0`（位置 tests/test_retrieval_enhanced.py:288，元组读数 (10.232, 10.208)）；**比值那一半在 0.9977 处绿着**——常数涨了 4 倍、比值没变，两条判据各看见一件事 |
| m3 每次查询先重新扫盘 | 一条红在「20 次查询 0 次调用」 |
| m4 记录签名复用失效（每个 tick 重读全部正文） | 一条红在「刷新不重读正文」（`open` 由 0 变 250）；同批被选的确定性那条**没红**——它判的是「两次一样」，不是「次数少」 |
| m5 写阶段退回串行 | 两条红全是结构量：`assert 1 >= 2`（本批新加的 `_max_in_flight`，tests/test_parallel_writes.py:92）与那条老见证（同文件 tests/test_parallel_writes.py:174，`writes did not overlap`）；**没有一条红是秒数** |

**同族两处搬家**：`tests/test_parallel_writes.py` 那条 `elapsed < 0.6` 早就是冗余的——同文件里 `test_parallel_writes_are_actually_overlapping` 已经用事件日志的结构量证过并发，所以这里改成同一个结构量（`_max_in_flight(events) >= 2`）加一条 15s 的活体线；`tests/test_subagent_streaming.py` 那条 `elapsed < 5.0` 想说的是「等的是取消而不是 30s 超时」，而这两种结局**按文字可分**（超时分支会写 `[TIMEOUT]`），于是判据搬到文字。**但本批第一次留下的活体线仍是一条秒表，而且被自己的复验抓红了**：写在 HEAD 的干净 worktree 里它红在 `elapsed < 15.0`，根因不是机器慢——取消分支自己就写着 `thread.join(timeout=15.0)`（minicc/agent/subagent.py:452），**合法的实现上限正好压在判据上**，这条线量的是「join 预算 + 负载」而不是任何回归。收口时把它移到实现上限之外（`elapsed < 60.0`，注释写明这只是「会回来」的兜底，判别由 status 与文字两半承担）。m5 实测：退回串行后红的是结构量那条（`assert 1 >= 2`）与它自己那条老结构见证，**没有一条红是秒数**。

**承重量**：新增 5 条、改写 1 条、同族搬家 2 处；`tests/test_retrieval_enhanced.py` 15 → 20。本批不动文档阅读器；`tests/test_doc_pointers.py` 收口时是 56 条门，M8-T47 落地后新增一条裸控制字节的门，现值 57 条（同一条记录里两处 56 的旧说法以本句为准）。全量 `.venv/Scripts/python.exe -m pytest -q`（先清掉所有 `__pycache__`，冷字节码）**1083 passed**，用时 630.03s；上一基线 1078 passed，差额 = 本批新增门数。本批的判据代码此后再没动过，动的是这段记录的文字与一处 docstring 的散文。**定稿之后没有重跑全量**：第三次冷跑在同一份树上跑过 12 分钟没有收尾就被停掉（这台机器当时在并行跑别的会话的测试），于是只重跑会读到这些改动的门与本批碰过的四个文件——`tests/test_doc_pointers.py`、`tests/test_retrieval_enhanced.py`、`tests/test_parallel_writes.py`、`tests/test_subagent_streaming.py`，冷字节码 **92.08s、86 passed**。**同一份全量代码今天的两次冷跑是 630.03s 与 371.38s，通过数一字不差，第三次连收尾都没收尾**——秒数是机器负载的函数，通过数才是代码的函数，这正是本批把判据搬离秒数的全部理由。定稿实测：**`checked 63 of 207`，八箱 `63/15/9/2/6/2/3/107`，23 条链接、856 条证据断言、19 个文档、228 个受版本控制的文件，`--check` exit 0**。反事实的测法：把本批的表格行、整节与上一批候选末尾的结案句三处一起撤掉，仍走出货入口 `doc_pointers.main(["--check"])` 重测全仓，读数逐格回到 `53 of 172`、八箱 `53/15/9/2/6/1/3/83`、链接 23 条、证据 830 条、exit 0——**本批对语料的净移动是 0 条真断言被新规则抓住**。被撤掉的正是未提交的工作，所以 git 在这里帮不上忙：脚本先快照文档字节、`finally` 里还原并复验 sha256 与快照相同（快照值只在运行当场打印，不抄进正文：文档一旦写下自己的哈希，「逐字节相同」就不可能成立了）。两组读数之差：处所引用 +10、标记 +35、词内标记 +24、证据断言 +26，全部由这段记录自己写下，逐条能对到本节里的句子——这才是它们进账而不是进红的原因。

**填充脚本自己也要答一次**：定稿数字得迭代到定点（写进文档的读数会被阅读器数到）。第一版按哨兵替换，收敛判据写成「替换后的文本与替换前相同」——可哨兵早在上一轮就被换成了字面量，于是每条 `.replace` 都是空操作，脚本当场宣布「定点达成」，而文档里还留着改标题之前的旧读数。**「不留残哨兵」那条断言救不了它**：哨兵不存在时它恒真。第二版把判据换成「每个读数模式必须命中恰好一次」——替换没着火就是红。这与 M8-T41 那条「交接箱只问有没有反引号，改成验发票」是同一个形状：**判据要问着火了几次，不是还剩几次没着火**。这条改完第一次跑就报 0/0/1（两个读数模式一个都没命中）——它先红给自己看，才红给别人。

**边界照写**：① 纯 CPU 的二次扫描没有任何门看得见（本批实测，六个读数的调用比值一字不差），两根判据的定义域是「文件系统调用」这一维，见下方「M8-T48 候选」。② `stat >= 250` 是下限不是等号：走树与签名读取的真实次数依赖 pathlib 的内部实现，写等号就等于把 CPython 版本变成判据。③ 那句「那条 120s 的活体线仍会红——在真挂死的时候」**是假的，本批收尾时核查后改掉**：断言行在挂死时根本到不了，红不了任何东西。实测支撑：`.venv` 里只有 pytest 9.1.1 与 pytest-asyncio，没有 pytest-timeout；`pyproject.toml` 里搜 timeout 零命中；`conftest.py:44` 的 `pytest_pyfunc_call` 只是 async 跑器、不含计时——**仓库里没有任何机制给单条测试计时**，所以一条真挂死的门会停住整场运行。那条线唯一的真实作用是「慢但最终返回」时红，而这件事它和负载分不开（见下方「M8-T50 候选」）。④ 计数器包的是五个具名符号，索引器哪天改走 `os.scandir` 或内建 `open()`，它会静默变 0——那正是 m1 的形状，仓库里代它承重的是另外两条门不是它自己。⑥ 那条「`[TIMEOUT]` 不在 summary 里」的缺席断言**现在有了正面见证**：`test_a_timed_out_subagent_labels_itself_as_timeout`（实测 call 时间 6.06s）。第一次造的见证跑不出来——`minicc/agent/subagent.py:144` 把截止夹成 `max(5.0, ...)`，而默认轮次预算下每轮 0.4s 的子代理在截止之前就自己结束了（4.5s 返回 `ok`）。**改法不是放宽判据，是把子代理做慢过截止**：每轮烧一秒，截止设 6.0s（在 5.0 下限之外，红不是被夹出来的）。见下方 M8-T49 那一段。⑦ 全仓 228 个受版本控制的文件里扫出 2 个裸控制字节（0x08），都在本文档、都是上一批那句「heredoc 把某个转义序列吃成退格符」自己写下的那个字节——**记录把它描述过的缺陷装进了自己**，本批写这段记录时又装进去一次（见下面 M8-T47 那条）。本批没动它：另一类问题，且 M8-T44 刚教过不要把两件事塞进一批。⑧ **量计时门的判别边际，第一次量错了对象**：`pytest --durations` 的 call 时间是整条测试函数的时长（含起 HTTP 服务、提交任务、关停），而门比的是函数体里那个 `elapsed`。拿函数时长代替，本批把两条其实宽裕的门读成了「余量不足、经不起负载」，错结论还提交了一次（`40d6bb0`），改账在此。**推论：凡引用时长做边际，先问「这个数是不是断言里那个变量」**——这是 M8-T44「同一份内容被两种量法读出两个数」的秒表版。

**M8-T47 也已落地**（收口之后）：门叫 `test_tracked_text_files_hold_no_bare_control_bytes`，扫 `git ls-files` 的文本文件，字符集 = 0x00~0x1F 去掉制表/换行/回车，**再加 0x7F**；全仓 228 个文本文件现在命中 0。修的过程翻出一条比「文档里藏着隐形字节」更硬的事实：那 2 个字节都不是「文档在描述退格符时顺手打出来的字符」，而是**两处本该写 `\b` 的地方被 heredoc 吃掉了**——一处是凭据形状正则 `\bsk-[A-Za-z0-9_-]{20,}` 的词边界（**文档里那条正则被静默改坏了**，它当时写的其实是一个真退格符加 `sk-…`），另一处正是那句「heredoc 把 `\b` 吃成退格符」自己引用的那个转义。两处已还原成字面 `\b`。**门自带非空守卫**：植一个 0x08 必须扫到、植 DEL 必须扫到、制表/换行/回车与 CRLF 必须不算——否则「扫到 0 条」与「扫描器坏了」读起来一模一样（这正是上一批太窄、这一批太宽两次踩的坑）。变异：往本文档种一个真退格符 ⇒ 红在这条新门；还原后复绿、`git diff` 对本文档只剩预期的文字改动。

**这条搬家在收口后又红了一次，读数在这里**：只含 HEAD 的 worktree 里 test_parent_waits_bounded_and_cancels_promptly 再次红（那次该组 20 条跑了 39.82s）。复现时我把这条门单独放在四个纯 CPU 忙等进程下重跑：它**通过**，但整条测试函数用了 **85.18s**——也就是说这台机器上「取消路径的一次调用」连同其收尾可以被拉到一分多钟，任何我写得出来的秒数兜底都在噪声里。结论与 M8-T45 一致：**这条门真正在判别的是 status == cancelled 与文字里没有 TIMEOUT 两半，秒数那半只能算「会回来」的兜底，且它已被两次负载证明会假红**。要它变成一条不撒谎的门，得让「回不来」这件事由外部计时（就是 M8-T50 那条：本批实测 faulthandler 中止在 Windows+pytest 下表现为崩溃，不是可读报告），而不是由门内的秒数承担。

**收口补测（第三次全量）**：`pytest -q` 冷字节码 **1085 passed / 531.61ss**，与「新增门数 = 差额」的算法对齐（1078 起点 → 计数门 5 条 → 超时正面见证 1 条 → 裸控制字节门 1 条）。在此之前，1085 这个数字在本批只是**按新增条数推算**——推算要照实标，补到实测才算完。

**看门狗已落地（本批收口之后）**：`conftest.py` 里两个钩子各管一半——到点只打印栈，不退出、不改世界；红由报告阶段用 pytest 自己量出的 call 时长判定，超过 MINICC_TEST_HANG_LIMIT 就把这条测试报成失败。默认 900s 远在实现预算之外（就是上一条边界⑧ 的教训）；把环境值设成空、0、负数或非法一律等于关，不替调用方猜数（M8-T22 那一格）。新文件 `tests/test_hang_watchdog.py` 三条门，正反两半都要：预算内不红也不打印（否则「什么都杀」的实现也能满足正向），超预算时 nested 会话保留报告并把慢的那条报成失败，第三条管环境语义。**全量在装上看门狗之后冷跑：1088 passed / 401.54s / exit 0**，默认上限没有误伤任何一条门。还留下一条流程教训：这段文字第一次写进本文档时被自己的阅读器判成 6 条门红、而且已经推送了一次，只能回退重写——**改完文档先跑一次检查再提交**，顺序不能反。

#### M8-T46 候选（下一批）：量两条秒表的判别边际，第一版量错了对象

本批量过两次，**第一次量的不是判据用的那个量**：`pytest --durations` 的 call 时间是整条测试函数的时长，里面包含起 HTTP 服务、提交任务与关停；而门比的是函数体里那个 `elapsed`。上一版因此写下「余量 3.65s / 4.38s、两条都经不起负载」，那两个数是函数的，不是判据的。**结论跟着作废**，正确的读数在下面这张表里（探针直接调用被断言包住的那次操作，空闲与四个纯 CPU 忙等进程并行各若干轮）。

| 门（上限） | 断言里的 `elapsed` | 加负载之后 | 它要区分的坏结局 |
| --- | --- | --- | --- |
| `tests/test_http_route_inventory.py:442`（10） | 0.00~0.02s（一帧、1286~1289 字节） | 0.00~0.02s | 等流结束——被 `read_sse_prefix` 自己的 10s 截止挡住 |
| `tests/test_core_tools.py:142`（15） | 1.34 / 1.36 / 1.34s | 1.45 / 1.56 / 1.38s | 修复前实测 22.4s（读管道到 EOF） |

所以本批**不做搬家**：SSE 那条的余量是两个数量级；bash 那条 docstring 里「上限故意离两种结局都远，套负载翻不动它」这句现在**有数了**（最坏正确读数 1.56s、坏结局 22.4s、界在 15s）。留下的两件事：① SSE 那条的界与实现的截止是**同一个数 10**——哪天有人把 `read_sse_prefix` 的 timeout 抬到 20s，这条门就当场变成负载函数，要改的是让界写成实现的函数而不是绝对秒数；② 归因错法本身入册，见本节「边界照写」那一段末尾。

**留下的两件事已做完一半：① 已改，② 已入册。**

① 那条门的界现在写成 `3 * deadline`，`deadline` 取自 `read_sse_prefix` 自己的默认关键字参数——那个数只存在于一处。给它配见证时先撞出一次**自我满足**：第一版自读断言搜的是逐字那句 `elapsed < 3 * deadline`，而我用来做变异的 `sed` 把**搜索者与被搜的那句一起改了**，于是变异之后门照样绿，见证形同虚设。把搜索串拆开写（`"elapsed < 3" + " * deadline"`）之后，同一个变异红在 tests/test_http_route_inventory.py:445，还原后复绿。**这是 M8-T36「指针自己就拼着那个编号」的构造门版本：自读式断言的搜索串，不能是它所读那句话的逐字副本。**

两条行为变异（把实现的默认截止改成 0.05 与 20.0）**都绿**：帧早在套接字缓冲区里，0.05s 也读得到那 1286 字节，而界是截止的 3 倍，永远追不上被它包住的读。**所以「界随实现移动」这条性质不可能被行为变异抓到，只能由构造门守着**（M8-T41、M8-T44 同一条规矩）。bash 那条 `tests/test_core_tools.py:142` 不动——它的界与两种结局的距离本批都已量过。

#### M8-T47 候选：受版本控制的文本里有裸控制字节，而记录装着它自己描述过的缺陷

上一批为「heredoc 把某个转义序列吃成退格符」写下的那两句里，退格符是**真字节**：本批扫全仓 228 个受版本控制的文件，命中 1 个文件 2 处 0x08，都在本文档。渲染时它什么都不显示，编辑器里看不见，`--check` 也不报——它是「文档里的字符是不是它自称的那个东西」这一类的第一例。**本批写这段记录时同类事故当场复发**：起草那句描述时，落盘的脚本里出现了一个真正的 DEL（0x7F）字节，而第一版扫描的字符集是「小于 0x20」，看不见它——把 0x7F 加进集合后重扫，仓库里仍是那 2 处（DEL 一个都没有），也就是说**这条候选的门必须把 DEL 算进去，否则它连本批这一例都抓不到**。改法两半：把那 2 个字节写成不会被渲染吞掉的文字，并加一条门——受版本控制的文本文件除制表/换行/回车外不得含控制字节（含 0x7F）。**复算这把尺子本批又错了一次**：收尾时重扫全仓，字符集写成「0x00~0x7F 去掉制表/换行/回车」，于是 228 个文本文件全部命中——上一批的错在太窄（漏掉 0x7F），这一次的错在太宽（把可打印字符当成控制字符）。同一条量法连着两批栽在「集合怎么定义」上，所以这条候选的门必须自带一组对照：**命中数必须恰好是「1 个文件、2 处 0x08」，既不许多也不许少**，否则扫描器坏掉时读数是绿的。把集合改对之后重扫，结果与上一批一致：1 个文件、2 处 0x08、0 个 DEL。本批不动它：一条计时门的批次里塞一条字符门的批次，两件事都会失去可核性（上一批刚为同样的合并付过一次账）。

#### M8-T48 候选：纯 CPU 的二次扫描今天没有任何门抓得到

本批那把新尺子量的是**每文件系统调用次数**，它的定义域到此为止。实测：把 `O(n^2 log n)` 的排序挂在 `_refresh` 之后（零额外系统调用），六个读数（三种条件 × 两轮）的调用比值全是 0.9954，一次不差；同场的 wall 比值与每文件 `process_time` 比值都无法把变异与对照分开（前者 2.09~4.64 对 4.01~4.02，后者 0.86~1.05 对 0.99~1.23）。**所以「构建变慢」这句话今天仓库里答不上来**，除非慢的那一半在磁盘上。可行的结构量得落在索引器自己身上：让它数自己对记录表做了几轮全表遍历——一个整数，随代码形状而定、不随机器负载而定，再配一条合成见证，与 M8-T35 给「比较行执行过」发明量法那次是同一类东西。**先量再定**：本批只留下六个读数与两把失败的尺子，没有动判据，也没有在新尺子的 docstring 里假装它什么都能量。

#### M8-T49（本批已落地）：超时分支的正面见证，必须让子代理慢过实现的 5s 下限

本批收口时登记这条候选的原因是「造见证的门自己先红了」；读实现后看清那不是缺陷而是**下限**：`minicc/agent/subagent.py:144` 把 `timeout_seconds` 夹成 `max(5.0, float(timeout_seconds))`，与同一处 `max(1, max_turns)`、`max(0, depth)` 是一家子钳制，所以 0.2s 的探针等于 5s 截止，而默认轮次预算（每轮 0.4s）让子代理在 4.5s 就交出 `ok`——**门没有说谎，是探针跑不进那一支**。
落地做法：新增一个每轮 `await asyncio.sleep(1.0)` 的 provider，截止设 `timeout_seconds=6.0`，于是一支永不收敛的子代理会在截止时仍在干活，超时分支必须自己认领结局。门断三件：`status == "timed_out"`、`"[TIMEOUT]" in summary`、`data["timed_out"] is True`，外加一条 60s 的「会回来」兜底（远高于实现预算：截止 6s + `thread.join(15s)`）。实测 call 6.06s，同文件 6 条全绿。**变异自证**：把 `minicc/agent/subagent.py` 超时分支 summary 里的 `[TIMEOUT]` 标签拿掉，这条门当场红（还原后 `git diff` 为空、复绿）——没有这一步，「它答上了那条缺席断言」只是一句自述。**这条见证的判别不依赖秒数**：秒数只用来确认它返回了，谁在什么时候结束由状态与文字说。

**账要算清，也要补上**：本批因此多了一条门。写这段记录时全量还没重跑（这台机器当时的负载让一次全量跑到 12 分钟没收尾），所以当时把 1084 标成**推算值**而不是补一个像量过的数。收口之后同一条命令、同样先清 `__pycache__` 冷跑一遍：**1084 passed，627.25s，exit 0**——推算与实测在此对齐，差额正好是那条新门。

#### M8-T50 候选：活体线要「到点就红」，不是「到点之前红」

上面那条边界③ 的核查留了一个真空缺：仓库没有给单条测试计时的机制，于是「防挂起」这句话一直由一条永远到不了的断言承担着。下一批的先量动作已写进任务表：先确认有没有可以就地用的计时手段（不新增依赖，装包属于改用户环境、不在授权内），再决定把看门狗放在这条门上还是全线共用；判据形状必须是**到点就红**，否则换一批数字还是同一件死代码。

**收口时真装上跑过一次，本批不落地（实测比计划更硬）**：把 conftest 的 pytest_runtest_protocol wrapper 与 dump_traceback_later(limit, exit=True) 装好，再起一个 nested 会话压 1s 上限——挂死确实被止住（rc 非 0），但在 Windows + pytest 下它表现为「Windows fatal exception: access violation」，不是裸进程里那种可读的 Timeout (…)! 报告，整场运行的报告一起丢。于是这条兜底不进仓库：conftest 与新门都已回退（git status 干净），边界③ 改后的说法保持成立——那条 120s 的线只在「慢但会返回」时红。下一步两条路：一是 exit=False 只打栈、再在 pytest_runtest_makereport 里把「打过栈」变成一条真正的红；二是交给 CI 的 timeout-minutes（改 CI 需用户批准）。

**【提交后复验】** 本批定稿提交之后，在一个只含 HEAD 的临时 worktree 里（那里没有任何 `__pycache__`，也没有本会话留在 Temp 的探针）重跑同一条检查命令与这批新写的门：读数与本段之前那句定稿逐字节相同，新门全部通过。这一步对本批不是仪式，理由和上一批同形但内容不同——本批改的是**判据用什么量**，而旧判据的红法依赖外部负载：只有从 HEAD 重新检出、重新编译，才知道这些门在一台没有并行负载、也没有我这台磁盘状态的机器上照样绿。反过来，本批记录里那些秒数（构建耗时、全量套件用时）不指望在这里复现，它们被写成机器负载的函数而不是内容的函数——这正是本批把判据搬离秒数的原因。这一段刻意不含处所引用与裸文件名标记：解释性散文自己会改分子，这件事上一批已经付过一次账。

### 第二十三批：两个「不是我们代码的错」的失败——一个真 bug 藏在半成品修复里，一个上游泄漏在会话末尾误报（2026-09-25）

**A. `{python}` 在 `shell=True` 下没加引号：真 bug，而且已经有一份半成品修复躺在工作树里**

工作树里有一份未提交的改动，加了 `render_python_command()`（用 `subprocess.list2cmdline` 加引号）和一个 `python_executable` 缝，
但三处都缺：① 没有任何调用点传这个参数；② docstring 写着「默认 `sys.executable`」，实现却只在显式传入时才渲染；
③ 嵌入的 grader 仍然自己做**未加引号**的替换。于是 bug 原地不动：默认 Windows 安装的
`C:\Program Files\...\python.exe` 被 `shell=True` 在空格处切断，cmd.exe 报 `'C:\Program' 不是内部或外部命令`，
**正确的工作区被判失败**（v2 里 7 条 `command_contract` 任务全中，全是 test-fix 类）。

完成口径：渲染一律发生在宿主侧（`python_executable or sys.executable`）；嵌入 grader 不再替换，改成
**看到未渲染的 `{python}` 就 `exit 2` 并打印原因**——同一个错不再有第二次机会。红→绿两半都钉进
`test_command_contract_quotes_an_interpreter_path_with_a_space`：加引号 → `passed`；同一条路径内联不加引号 → `failed`。

**测试自己踩的坑也记一笔**：第一版把 `sys.executable` 直接写进 `.cmd` 包装器，但本仓库路径含中文，而 `.cmd`
由 cmd.exe 按 OEM 代码页读取 → 路径先被弄坏，测试红得与引号无关。改成包装器只引用环境变量（纯 ASCII 文本）后正常。
这类「测试的脚手架比被测对象更脆」的失败，必须先把脚手架修到不可能误报，再谈红绿。

**B. 会话末尾那次强制 GC 会把 pytest 自己的 scandir 泄漏算到我们头上（上游缺陷）**

现象：`pytest -q -W error` 偶发 `PytestUnraisableExceptionWarning: unclosed scandir iterator`，把一次全绿的运行判红
（2026-09-22 一次、2026-09-25 两次，此前被当成「环境偶发」放过）。开 tracemalloc 后分配点明确落在
`_pytest/pathlib.py:177 find_prefixed`——它是个**生成器**，`os.scandir` 没进上下文管理器，pytest 的数字临时目录清理
（`cleanup_candidates`）会把它半途丢弃，迭代器只能等 GC。

两条**走不通**的路先排掉，避免后人重走：
- **ini `filterwarnings` 豁免无效**：pytest 源码写着过滤器优先级「命令行 > ini」，`-W error` 会盖掉 ini 里的 `ignore`；
- **钩子豁免不存在**：`pytest_unraisable_exception` 在 pytest 9 已被移除。

落地口径：在 `conftest.pytest_configure` 里把上游自己留出的 stash 键 `gc_collect_iterations_key` 设为 0，
**只跳过会话末尾那一次强制 GC**（`pytest_unconfigure` 里的 `gc_collect_harder`），每测试阶段的 `collect_unraisable`
（setup/call/teardown 三处）一字未动。

**承重量（这条最要紧）**：临时写一个**真的泄漏 scandir 的测试**（`next(os.scandir("."))` 后丢弃）→ 仍然红，
`1 failed`，警告归属到那个测试本身。也就是说这次豁免**只**拿掉了「会话末尾把 pytest 自己的垃圾算到会话上」那一格，
没有把真信号一起吞掉。

**配套不变式**（否则豁免就成了一张空白支票）：新增 `tests/test_resource_hygiene.py` 两条 AST 门——
`minicc/` 与 `scripts/` 不得出现 `os.scandir`；每处 `iterdir()` 必须在同一表达式里被消费（`for`/推导式/`list()`/`sorted()` 等），
带 `>= 4` 的下限防空扫描。**变异验证**：临时在 `scripts/` 下放一个同时犯两种错的脚本（两种错各一处：未进上下文管理器的
`os.scandir`、绑定后未耗尽的 `iterdir()`；跑完即删，不在仓库里）→ 两条门同时红并逐字点名该文件与第 12 行，删除后绿。
**这条记录自己踩了一次文档指针门**：第一版把那个临时文件的路径写进了本段，而它已经删了，于是 `doc_pointers --check`
在 CI 上判它悬空（见第二十三批 C 段的收尾）——**证据里的路径也是一条断言**，写"我删过一个文件"时不能顺手留下它的路径形状。

**基线**：`tests/test_bench_tasks.py` **13 passed**；`test_bench_tasks + test_resource_hygiene + test_ci_hygiene + test_http_surface + test_http_route_inventory` 合计 **108 passed**（`-W error`，无 scandir 误报）。

**C. 主干 CI 红了十几个小时，原因是 CI 里少一个包，而开发机上恰好有**

查项目状态时顺手看了流水线：最近若干次 push 的 `CI` 全是 **failure**，红的不是新代码，是 `Python tests` 这一条的两个腿都红。
`gh run view --log-failed` 取到逐字原因：

```
E  usage: -c [global_opts] cmd1 [cmd1_opts] [cmd2 [cmd2_opts] ...]
E  error: invalid command 'bdist_wheel'
```

`tests/test_packaging.py` 用 `setuptools.build_meta` **在测试进程内**构建 wheel，所以 `bdist_wheel` 这个命令必须在**测试环境本身**存在。
GitHub 的 Python 3.11 镜像自带 setuptools 低于 70.1（那个版本还没把 bdist_wheel 收进自己），而 dev extra 里没有 `wheel`——
于是两个腿全红；开发机上因为 `wheel` 恰好装着（0.48.0），11 条打包测试一直是绿的。

**先复现再修**（不靠推断）：一次性 venv + `setuptools==69.5.1` + 不装 `wheel` → 同一条构建命令逐字复现
`error: invalid command 'bdist_wheel'`；装上 `wheel>=0.41` → 同一命令立刻打出 `wheel: minicc-0.1.0-py3-none-any.whl` / `sdist: minicc-0.1.0.tar.gz`。

落地：`wheel>=0.41` 进 dev extra（与 `httpx` 同一类缺陷——**测试在依赖一个碰巧装着的包**），
并加 `test_wheel_is_declared_because_packaging_builds_in_process` 把这条钉住，防止下次被当作「多余依赖」删掉。
`pip check` 通过；`pip install -e ".[dev]"` 通过；本机 `tests/test_packaging.py` **11 passed**。

**这条的教训比修复值钱**：**开发机上的绿，证明不了 CI 的绿**——凡是"构建/打包/版本"这类判据，
只要它读的是环境里碰巧存在的东西，就必须在声明文件里写死，或者干脆在干净环境里跑一次。

**接线后的第一次真跑还顺手抓出三处悬空声明**（都是文档侧，不是代码）：两处是本批 A/B 段自己写的
——把那个"跑完即删"的临时验证文件按路径写进了记录，而它已经不存在；第三处是别人写的一句指向
**本文档并不存在的编号**的「见」。三类都由 `doc_pointers --check` 在 CI 上判红并逐字给出文件与行号。
修法不是加豁免，而是把话说准：删掉不存在的路径形状、把「见」改成指向真实存在的段落。
**顺带得到一条写作纪律**：连"我删过一个文件"这种话，只要留下路径形状就变成一条断言——
证据写得越具体，越要保证它指向的东西此刻真的存在。



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

**2026-09-23 更新**：那次整体复核已经做起来了——第一到第四批覆盖 M1-M3、M4、M5-M7，第十八批覆盖 M8。
当前只剩**一条**退出标准没有数据支撑，且它需要的是一次真模型全量评测（成本可观、受本机 10 RPM 配额约束）：

| 未达成项 | 现状 | 需要什么才能结案 |
| --- | --- | --- |
| M6-4「30 个 fixture 的性能 P95 不超 M4 基线 +15%」 | ✅ 2026-09-25 结案：24 条干净全量（零 429 死亡），p50 50.2s / p95 ~107s 在基线 +15% 线内；pass@1 13/24，失败 11 条里 10 条 grader 实际通过（详见状态表该行与 2026-09-25 节） | 无（已结案；主导失败模式转为两条新候选：评审可满足性、重复判定提前停止） |
| M3-3「`grep -rn sk-` 零命中」 | ❌ 标准本身不成立（命中 19 167 次全是 `task-<hex>` 里的子串），已由 `scan_credentials()` 换成形状判据结案 | 无（已用可执行判据替代） |
| M4-3「POST `/api/*` 覆盖率 100%」 | ✅ 已从「算不出来」转为实测通过（`coverage[toml]` 进 dev extra；分派点 GET 20/20、POST 14/14）。**M8-T35 换了口径再确认一次**：原来的分派点数问的是「比较行执行过没有」，一条走到链尾的请求就能喂满（实测 14/14 对 0/14），现在问「分支体进过没有」，两个口径同为 100%，且量法已进仓库（`scripts/route_coverage.py --check`） | 无（已结案；把 `--check` 接进 CI 需要动流水线，留给用户定） |


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

## 2026-09-25：M6-4 全量结案（24 条干净真模型评测），并登记四条由数据指证的候选

第五批留下的唯一未结退出标准 M6-4 在本日结案。这是**第一次**在 M8-T16 限流退避修复之后跑全量，
也是本仓库第一次拿到 n=24 的可信分位数。

### 量法与读数

- 命令：`python -m minicc.benchmarks --suite v2 --run --results output/m6_4_full.results.json`，分三批
  （`--max-tasks 8 / 16 / 全量`）串行执行；runner 逐条落盘、按 metadata（code_revision + config hash +
  runtime source hash）匹配续跑，三批共用同一 `code_revision=46a9a8ab8`，无版本混杂。
- 零 429 死亡：M8-T16 的 15/30/60/60 退避在 10 RPM 配额下全程兜住（第五批 4 条 429 全灭的场景未再出现）。
- 单任务消耗：`total_tokens` 均值 87 389 / 中位 95 527，全程 2 097 337 tokens（step-3.7-flash，reasoning=high）。
- 延迟：p50 **50.2s**、p95 **~107s**（nearest-rank）、最大 186.9s——全部在 M4 基线（115s/826s）+15% 线内，
  **性能标准通过**，M6 fan-out 护栏从此有了真正的全量基线。
- pass@1 **13/24 = 0.5417**、grading_coverage 1.0、false_completion_rate 0、执行完成率 0.5417。

### 失败分解（11 条）——主导模式不是编码能力

| 类别 | 条数 | 任务 |
| --- | --- | --- |
| 完成守卫循环判死，隐藏 grader 实际通过 | 8 | config-json / greet-function / env-example / dockerignore / package-init / package-manifest / gitignore / schema-json |
| 其他守卫判死，grader 实际通过 | 2 | version-exact（恢复阶段无新证据）、fix-uppercase（修改后未验证） |
| 真编码失败（grader 不过） | 1 | multi-config |

「grader 实际通过」的判据是任务记录里的 `objective_oracle`（`passed=true` 且 case/exit 干净）。按这个口径，
**交付正确率 23/24 = 0.958，而严格验收 pass@1 只有 0.5417**——两者之间 10 个百分点的差全部消耗在
「评审要求运行测试 → fixture 工作区没有可运行的客观检查 → 验证跳过 → 评审继续要求 → 循环到上限」这条
不可满足循环上（9 条死在同一句上限文案）。5 条的 `review_rounds` 逐字重复同一个 `missing`，单条最多烧掉
179 239 tokens（package-init，22 轮）。

### 由此登记的四条候选（按预期收益排序）

1. **评审可满足性注入**：验证计划客观判定「工作区没有可运行检查」（`verifier.py:124` 的 `skipped_reason`）
   时，把这一事实注入完成评审提示词——不得把「运行测试」当作 `missing`，应基于修改证据判断。这是根因修复：
   `objective_oracle` 已经证明这 8 条的产物是对的，只是永远无法让评审满意。
2. **M8-T19 重复判定提前停止**：本轮评测提供了该条等了三批的「可满足性见证」——`greet-function` 等 5 条
   `completion_verdict_repeated` 场景（逐字复读 + 零新增活动）真实出现且代价可测（每条多烧 2-3 个 agent 轮）。
   停止策略从 `observe_only` 升级为「重复即按上限停止」，语义仍是「未收敛」而非「完成」。
3. **DAG 节点预算旁路**（P2-8 漏网复核确认仍在）：`web.py` 的 `run_node` 给节点 Agent 全 `None` 的
   `Budget`，与 chat 路径（config 驱动 + soft 限制）不一致。修法：kwarg 与 Budget 双设 12 轮 / 300s 硬界
   （比子代理 24 轮 / 600s 更紧，节点是单职责单元），soft 限制沿用 config。
4. **per-edit 备份永不清理**（P2-8 漏网复核确认仍在）：`editor.py` 的 `_backup` 每次编辑落盘
   `.minicc/backup/` 且全仓无任何保留策略。修法：写后裁剪，保留最近 200 份，裁剪失败降级为警告不阻断编辑。

顺带如实记录：version-exact（恢复守卫）与 fix-uppercase（修改后未验证）两条走的是**另外两条**守卫路径，
不在上面两条评审修复的射程内，留作后续候选；它们的 grader 同样通过，说明守卫语义（没有新鲜证据就不许交付）
在按设计工作，只是对「产物已正确」的场景偏保守。

### M8-T55 注记：双通道不是重试，是记账边界的移动

用户提供的真实场景驱动了本批：付费 API 与 Step Plan 套餐（Credit 月池）是同一把钥匙后面的两个独立额度池，
主通道耗尽时任务直接以 402 死掉——评测语料里的任务没做错什么，死的是「额度」这个执行条件。

**调研结论（实测，非文档转述）**：`https://api.stepfun.com/step_plan/v1` 与付费 `/v1` 同 key 可通
（models 200 / chat 200）；官方无 API-Key 可调的套餐余量端点——13 个候选路径（usage/credits/quota/
billing/subscription 等）全部 404，用量只在控制台网页。因此「查余量」不可实现，「按通道记账 + 用尽切换」
可实现，本批只做可实现的部分并如实写明边界。

**判据是本批的核心资产**：429 有两种语义——普通限流（慢下来，重试语义保留）与 Credit 上限
（池子空了，重试无意义）。两者靠报文错误码区分（insufficient_credit /
project_credit_limit_exceeded / member_project_credit_limit_exceeded），402 无条件判额度死亡。
**粘性是刻意的**：月池按月发放，进程内一次转换即可，反复探测只会烧时间。

**一条测试教训**：integration 断言精确的 agent 轮数（写后强制「检查 diff/验证」nudge 的轮数）在
单测与全文件运行间漂移（2 对 4）——nudge 是循环内部行为，对断言者不可见也不该可见，断言只设下界。
这与 M8-T45「量机器负载的秒表换成不看秒数的尺子」同构：量你拥有的东西。

### M8-T53/T54 的真模型 A/B 复测（2026-09-25，套餐通道）

把 M6-4 全量里 8 条因不可满足循环判死的任务，用修复后代码在 Step Plan 套餐通道重跑
（`--task-id` 定向，`output/ab_m8t54.results.json`）：

| 项 | 修复前（M6-4 全量） | 修复后（A/B 复测） |
| --- | --- | --- |
| 通过 | 0/8 | **8/8** |
| tokens 合计 | 1 044 335 | 493 586（**-52.7%**） |
| 单条 tokens 区间 | 101k–171k | 35k–81k |

每条任务的 tokens 都在下降——下降的部分正是原来烧在「评审要求跑不存在的测试 → 循环到上限」上的轮次。
按 pass@1 口径，v2 全量在修复后的期望值从 13/24 移到至少 21/24（其余 13 条未重跑，按原样计入）。
这次复测同时验证了 M8-T55 套餐通道作为主通道跑完整个评测的能力。

### M8-T56 登记：仍由守卫判死但 grader 通过的两条残余

version-exact（恢复阶段无新证据）与 fix-uppercase（修改后未验证）走的是 agent 循环自己的守卫路径，
不在评审器修复的射程内。它们量的是另一件事：产物正确但执行路径不满足守卫对「新鲜证据」的要求。
是否值得为它们放宽守卫，需要先回答「守卫是否在保护真实用户场景」——留作候选，不做无据放宽。

### M8-T56 结案：给守卫一条能走到证据的路，而不是放宽守卫（2026-09-25）

两条残余量的是同一件事：守卫对「新鲜证据」的要求没错，缺的是模型对「什么算证据」的知情权。
原来两条执行器提示只有「运行最小且直接相关的测试或验证」——不点名任何一条
`is_verification_evidence` 认得的命令；fixture 工作区没有测试套件时，这句话指向的检查根本不存在，
模型于是要么直接结束（判死），要么跑一个不算证据的脚本（还是判死）。修法是把提示词接到门上：

1. 写后提示与「未验证就想结束」的提示抽成 `POST_WRITE_VERIFICATION_NUDGE` /
   `PRE_FINISH_VERIFICATION_NUDGE`，共用同一份 `VERIFICATION_CHECKER_EXAMPLES`
   （pytest / compileall / mypy / `node --check` / `npm run test`）；
2. pre-finish 提示补上守卫认得的退路：**工作区没有任何可运行的检查时，用
   `python -m compileall` 校验改动文件语法**；
3. 明写「直接执行脚本不算验证证据」，不给 `python shout.py` 当交付证明的机会。

**判据（先红后绿）**：`tests/test_verification_nudge_contract.py` 3 条，全部从一次真实 `run_agent`
运行里读回注入的用户消息——**不 import 那两个常量**，否则测的只是常量还在不在——再把括号里的示例
逐条代入占位符后交给 `is_verification_evidence` 验。把 `loop.py` stash 回 HEAD 重跑：2 条红
（提示里没有任何示例 / 没有退路）、1 条绿（第三条是门本身的性质，本来就该恒绿）；修复后 3/3。
全量 `.venv` 下 `python -m pytest -q`：**1100 passed / 321.42s**。

**真模型复测**（`--task-id v2-version-exact --task-id v2-fix-uppercase`，与登记时同两条）：

| | 登记时（M6-4 全量） | 修复后 |
| --- | --- | --- |
| 通过 | 0/2 | **2/2**（两次独立运行均 2/2） |
| 轮次 | 判死在 22 轮上限 | 16 轮 / 9 轮 |

边界如实记录：n=2、每种口径各一次。两次运行的 `runtime_source_sha256` 分别是 `a548e861…`
（提示词改完、尚未抽常量）与 `1d536c1c…`（抽常量后），内容差异只有示例排版与多出的两条示例，
故并列入册而不是只记最新一次。这证明的是「这两条不再判死」，**不证明守卫变松**：
`test_git_status_does_not_clear_post_write_verification` 等既有守卫用例一条未改、全绿。

**顺带量到的环境事实**：`.venv` 才是这套门的解释器。用系统 Python（`C:\Program Files\...`）跑全量
得到 2 failed + 7 errors，三条失败指向同一件事——`{python}` 占位符替换后没有加引号
（完整修复与两半红绿见下方「第二十三批」A 段）。


### 第三十批 M8-T57：文本模式捕获把「读不到」伪装成「读到了空」（2026-09-25）

**发现方式**：不是崩在功能上，是崩在「全量跑一次」上。不带 `PYTHONIOENCODING` 的冷跑里，
`tests/test_bench_tasks.py::test_command_contract_quotes_an_interpreter_path_with_a_space`
先红——`subprocess.run(..., text=True)` 不写 `errors=` 时，子进程的字节用**父进程的语言代码页**解码，
遇到非法字节异常抛在 subprocess 自己的读线程里，`run()` 照样返回 `returncode=0`，
而 stdout 已经被吞成空。`-W error` 把线程异常变成 `PytestUnhandledThreadExceptionWarning` 才让它显形。

**三条实测读数**（本机 `locale.getpreferredencoding(False) == cp936`）：

| 生产者 | 字节 | >0x7F | 不写解码器 | 写 utf-8 |
| --- | --- | --- | --- | --- |
| `git log -8 --format=%s` | 739 | 291 | rc=0、0 个字符 | 545 字符 |
| bench grader 的 stdout | 178 | 78 | 标记行整条丢失 | 完好 |
| `git worktree list --porcelain` | 108 | 12 | 路径 22 字符（真值 20） | 20 字符 |

第三行是这个类里最坏的一半：字节**恰好能被 cp936 解出来**时不抛任何异常，调用方拿到一个
看起来合理的错答案（四个汉字被解成六个乱码字）。第二行是用户可见的危害：被评分的命令回显一条
中文报错，`_COMMAND_CONTRACT_GRADER` 的 `proc.stdout` 变 `None`，`stdout_contains` 判不过，
一个退出码正确、标记也打印了的产物被判 `COMPLETE:0`。

**修法按生产者是谁分两类**（抄的是仓库已有的形状，见 `minicc/tools/git.py` 的
`encoding="utf-8", errors="replace"`）：git 输出的编码是已知的 → 点名 codec；子进程是别人的
（shell 命令、任意 verify 脚本）→ 只声明 `errors="replace"`，不替孩子挑编码。
落地 22 处：`minicc/` 5 处文本模式捕获加嵌入 grader 脚本里的 1 处、`scripts/` 1 处、
`tests/` 15 处（其中 2 处补的是子端编码声明）。

**门扩到三个根，因为门自己也是受害者**：把 `errors=` 只加到 `minicc/` 之后，同一场冷跑里
`tests/test_doc_pointers.py` 的两条仍然红——它们写了 `encoding="utf-8"` 却没写 `errors=`，
孩子按 cp936 写报告、父亲按 utf-8 读，整份报告被吞：一条读到
`assert "DANGLING" not in result.stdout` 抛 `TypeError: argument of type 'NoneType' is not iterable`，
另一条在 `result.stdout.strip()` 上抛 `AttributeError`，而 **`returncode` 那一条断言是先通过的**
（检查器确实跑成功了，被丢掉的只是它的报告）。补上 `errors=` 后流回来了，
但 `re.search(r"(\d+) 「见」 markers")` 还是返回 `None`——报告末行那对中文引号被解成了替换字符。
**一条门的绿不该依赖一个没人被要求设置的环境变量**，所以 `scripts/` 与 `tests/` 一起进射程。

**新增的第二条判据是从这条链里长出来的**，不是预设的：`encoding="utf-8"` 只钉父端解码器、
孩子是 `sys.executable`、又没声明 `PYTHONIOENCODING` ⇒ 半个修复。它当场又抓到两处
先前任何判据都看不见的站点（`tests/test_hang_watchdog.py`、
`tests/test_route_coverage_measurement.py`——它们有 `errors=`，因此逃过了第一条判据）。

**判据**：`tests/test_subprocess_decoding.py` 11 条。AST 清单而非 grep（grep 分不开字节模式与
文本模式，字节模式不可能误解码）；模块级字符串里再解析一次 AST（嵌入 grader 是唯一能看见
`bench_tasks.py` 里那一处的办法，且由合成见证钉住"这一趟是承重的"）；地板常量按实测钉死
（29 条文本模式捕获、2 条嵌入），清单只有一条根有贡献时另一条根判红；植入违规 + 合规孪生 +
字节模式不报，三向对照。行为见证三条，全部打生产宿主：非法字节后标记行仍要读得到（吞流那半）、
被评分命令回显非法字节时 `grade_command_contract` 仍要判过（grader 内那半）、
中文 worktree 路径原样返回（乱码那半，语言环境相关）。

**变异自证 6 次，每次都被对应判据抓住**：去掉 `_run_grader` 的 `errors=` → 2 红（结构 + 行为，
`result.stdout` 读回 `None`）；去掉嵌入 grader 的 → 2 红，行为那条读出
`{'passed': False, 'exit_code': 1}`（正是"正确产物被判失败"的原始症状）；去掉 worktree 的
`encoding="utf-8"` → 2 红，中文 worktree 路径判红 + 结构判据判红（上表第三行是同一现象的读数）；去掉 `benchmarks.py` 与
`behavior_bench.py` 的 `errors=` → 各 1 红（结构判据，二者形状与已具行为见证的宿主相同）；
去掉子端编码声明 → 1 红，还原后字节级一致。

**边界照写**：① 只声明 `errors="replace"` 的站点，中文输出会变成替换字符——吞流没了，
乱码还在，这就是 M8-T58 那条候选的同一件事，本批三组读数里第 2 组就是它。
② `tests/` 里剩下的文本模式捕获由判据覆盖，但 `minicc/` 之外**没有任何行为见证**——
它们的绿目前是结构判据 + 合成门撑着。③ 本门文件自我豁免（它是唯一故意写违规字符串的地方），
代价是往里加一条真捕获不会被抓。④ 两次冷跑读数分别是「修复前 2 failed + 1113 passed + 2 errors / 541.22s」与
「修复后 1118 passed / 350.03s（exit 0）」，但**这两个数不可逐条相减**：前一次运行里本门文件还
没有第二条判据与它的三条合成见证，两次收集的测试数本来就不同。可比的是同一件事——
两条 `tests/test_doc_pointers.py` 的红在无 `PYTHONIOENCODING` 的冷跑里从「有」变成「无」。
⑤ 中途一次定点填充把 `env=` 加成了重复关键字，`SyntaxError` 在收集期就炸——
它不是变异的红、是零证据，因此每次定点填充之后补了一道 `compile()` 复验（15 个被改文件全过）。

### 第三十一批 M8-T59：双通道此前只有 grep 撑着，两条请求路径零行为见证（2026-09-26）

**发现方式**：M8-T57 收尾时复核 M8-T55，问的是「三条请求路径真的都走 `_active_client()` 吗」。
答案今天是对的——但复核过程暴露了另一件事：**这个「对」字此前没有任何一条测试能回答**。
`tests/test_plan_channel.py` 原有的 6 条测试全部写死 `protocol="chat_completions"`、
全部把 `_plan_client` 直接注入进去，于是 responses 的两条路径（非流与流）
和「套餐客户端到底是用什么凭据建出来的」这段惰性构造，全是零行为见证。

**先量的三个数**：provider 里的 SDK 请求点 3 个；仓库里带套餐参数的测试文件 1 个，
其中 `protocol=` 只出现 1 次（就是那条 chat_completions）；把 `plan_base_url` 交给 provider
的构造点 2 个（`minicc/main.py:626` 与 `minicc/web.py:1006`），而 `MINICC_PLAN_BASE_URL`
这个键名在 tests/ 里**一次都没被读过**。

**判据**：`tests/test_plan_channel.py` 6 条 → 13 条，新增的 7 条分三层。
结构层用 AST 扫请求点（地板常量 3），要求每一点的客户端表达式里出现 `_active_client()`；
构造层把 `AsyncOpenAI` 换成记录用的假类、provider 一个客户端都不注入，断言
「建了两次、第二次带的是套餐 key 与套餐 base_url、且 `max_retries=0`」；
行为层给 responses 非流与 responses 流各一条 402 切换，假客户端记录**调用落在哪个面**，
所以「悄悄退回 chat 面并且绿」这条路被堵死。再加扫描器自身的两向反证：
前缀更长的违规写法必须被抓到，无关的 `session.create()` 必须不被误抓。

**扫描器第一次跑就红了一次，红的是我自己写的门**：初版把「整条属性链等于已知链」当作请求点判据，
于是植入见证里的 `self.client.responses.create(...)` 扫出来是空——这条门最该抓的形状恰恰看不见。
改成尾链匹配后，`self.client.` / `self._client.` / 局部变量 `client.` 三种写法各自被抓，
合规孪生与无关 `.create()` 不误抓。

**变异自证 9 次**（每次还原后字节级一致）：非流请求点改用固定客户端 → 2 红（结构 + 该路径行为）；
流请求点 → 2 红；chat 请求点 → 4 红（结构 + 构造 + 两条旧测试）；
`_active_client` 整体短路 → 5 红（4 条行为 + 1 条旧）；
**套餐客户端改用付费 base_url → 只有构造见证 1 红、结构门全绿**——这条是本批的关键读数，
它证明新写的行为见证不是 grep 的复读机；套餐客户端改用付费 key → 3 红；
两个构造点改用不再传它的名字：CLI 的 `plan_base_url`、web 的 `plan_base_url`、web 的
`plan_api_key` 各改一处 → 三次各自 1 红（都落在构造门上）。

**真模型复测**（stepfun，`protocol="responses"` 锁定，2 次请求）：非流与流都跑通，
`protocol()` 事后仍是 responses（没有回退），`channel_status()` 记到 paid 2 requests / 307 tokens。
顺带拿真实 SDK 对象的属性名对齐了新写的假响应形状：顶层 `id/status/model/output/usage`、
usage 的 `input_tokens/output_tokens/input_tokens_details`、output item 的 `content/type`、
content part 的 `text/type` 全部同名——**假形状是真形状的子集，不是照想象写的**。
`.env` 一侧读到的事实（只打印布尔、不打印值）：套餐通道的两个键在本机都已配置，
所以 M8-T55 那条腿不是装饰。

**边界照写**：① 构造门只验「参数被交出去了」，不验「交出去的值非空」——空串照样过门，
运行时判空发生在 `_has_plan_channel()`；本机实测两键均非空。
② `AnthropicProvider` 的两个构造点（`minicc/main.py:618`、`minicc/web.py:998`）没有套餐通道，
额度耗尽时它没有第二条腿；本批只把这件事量出来记在册上，不替它决定语义。
③ responses 流式的**真实事件序列**没有被门覆盖（门用的是单条 delta + completed 的合成形状），
真模型那一次只证明「跑得通、形状对得上」。④ 全量冷跑（`-W error`、无 `PYTHONIOENCODING`）：
**1125 passed / 363.25s**，与上一批的 1118 恰好差本批新增的 7 条。

---

## 第三十二批（M8-T48）：检索的候选集第一次有了度量，而一条老门被证明永远不会响

### 1. 这一批是在还上一批的债

M8-T45 把检索的计时门换成「每文件系统调用次数」之后，自己在 docstring 里写了一句定义域：
这套仪器看不见**不花 syscall 的慢**，并把下一批登记成 M8-T48。这批就是那笔债：
把「一次查询到底碰了多少条记录」变成仓库里可执行的量，而不是我此刻口头承诺的线性。

### 2. 先量，再改（改代码之前读到的数）

真实仓库（`get_evidence_index(D:\面试项目\minicc-codex)`，未改任何文件）：

| 量 | 读数 |
| --- | --- |
| `files_indexed` / `symbols_extracted` | 227 / 4874 |
| `last_build_ms` | 464.72ms（同一台机器另一次 725.93ms） |
| 每次查询交给打分器的记录数 | 227（三条查询全是 227，包括返回 0 条命中的那条） |
| 把表截到 113 条后 | 113 —— 计数跟着表走 |
| 单查询墙钟（227 条真记录） | 约 9–12ms |
| 单查询墙钟（300 条合成小文件） | 3.85ms |

合成树（300 条记录）上，命中 1 次的查询、命中 20 次的查询、命中 0 次的查询，
打分次数都是 300；只有空查询是 0（`plan.is_empty` 在进入循环之前返回）。
这两组数一起决定了这批门的口径：**每查询成本是表的函数，不是答案的函数**。

### 3. 落地的四条门和一个仪表

全部在 `tests/test_retrieval_enhanced.py`，24 条（原 20 条）。仪表是 `_scorer_spy`：
把 `minicc.agent.retrieval._score_record` 换成记录参数的替身，`finally` 还原并**复验还原成功**——
`search()` 每次迭代都按模块属性取打分器，所以这是唯一能看见**候选集**而不是它输出的仪器；
命中列表里看不见的东西（预筛、提前退出、重复打分）在这里都藏不住。

| 门 | 钉住的合同 |
| --- | --- |
| `test_every_search_scores_the_whole_table_regardless_of_the_answer` | 三种命中数的查询都走完整表；空查询 0 次；把表截到 60/20/5/1 条时计数跟着表走；**报表条数 == 被走的表条数** |
| `test_a_match_beyond_the_limit_is_still_offered` | 排序上限不得变成扫描上限：命中文件在扫描顺序最后一名（从 `index._records` 里取，不靠 `os.walk` 的运气），`limit=8` 仍要返回它 |
| `test_freshness_alone_never_fabricates_a_hit` | 零词重叠的新文件会被打分、但不会被返回；新鲜度只是同分时的加分，不是相关性证据 |
| `test_resident_guidance_is_a_last_resort_not_a_top_hit` | guidance 的常驻加分（实测 `AGENTS.md` 5.0，reason `guidance-resident+fresh`）**高于**一条真实的 content 命中（4.0），它之所以无害，仅仅因为 `search()` 只在真实命中为空时才采用常驻证据 |

后两条合同此前一条测试都没有：`grep guidance-resident tests/` 在落地前是 0 命中。

### 4. 仪表自己的洞，是变异抓出来的

第一版把 spy 的读数与 `index._records` 比——这是**自我指涉**：那个列表正是循环走的东西，
所以「build 时把表截断到前 100 条、`stats` 照报全量」这一形状（N2）照样绿。
补的是一条恒等式，不是一个新的绝对数：`len(index._records) == stats()["files_indexed"]`，
同时把样本表从 40 条提到 120 条，让截断点真的落在表中间。

### 5. 七条变异读数（每条只改一个字节级锚点，跑完整文件，还原后复验 sha256）

| 变异 | 红在哪 | 谁在守 |
| --- | --- | --- |
| M1 扫描被排序上限截断（`self._records[:limit]`） | 5 红：新门 2 条 + 老门 `test_limit_boundaries_and_empty_query`、`test_thousand_file_index_builds_within_budget`、`test_searching_a_built_index_touches_no_disk` | 老门已在守——诚实记录：新门的增量是把「从结果集推断」换成「对候选集测量」 |
| M2 去掉「未命中即返回 None」的守卫 | 4 红：新门 3 条 + **老门 `test_stopwords_are_removed_from_queries`** | 见第 6 节，这条是老门修好之后才红的 |
| M3 常驻 guidance 永不出场 | 1 红：`test_resident_guidance_is_a_last_resort_not_a_top_hit` | 只有新门 |
| M4 常驻 guidance 混进真实证据参与排序 | 2 红：新门 1 条 + `test_cjk_bigram_query_hits_expected_file` | 新门是正面见证 |
| M5 去掉空查询短路 | 1 红：`test_every_search_scores_the_whole_table_regardless_of_the_answer` | 只有新门 |
| N1 每条记录打分两次 | 3 红：全部是新门 | 只有新门——这是「不花 syscall 的浪费」第一次有名字 |
| N2 build 时截断表、报表照报全量 | 2 红：新门恒等式 + `test_searching_a_built_index_touches_no_disk` | 补恒等式之前这条**全绿** |

不红的变异等于零证据，所以每条都记了它到底让谁变红。

### 6. 真发现：一条声称了这个合同、却永远不可能响的老门

`tests/test_retrieval_enhanced.py` 里 `test_stopwords_are_removed_from_queries` 最后一行原本是

```python
assert all("notes.md" != hit.path for hit in noisy)
```

它上面的注释写着「"the" 不得把 notes.md 拉进来」。但被索引的键带目录，`hit.path` 是
相对路径而不是文件名，所以这个断言恒真。证据不是推理，是两次实测：

```text
状态            noisy 的返回                                     该行结果
源码干净        2 条命中                                          绿（应当绿）
M2 去掉守卫     6 条命中，含 ('docs/notes.md', 'fresh', 3.0)      仍然绿
```

（那两条路径只出现在上面的围栏输出里，故意不写成反引号指针：它们指向 `tmp_path`
夹具中的临时文件，不在仓库里，写成证据指针就会被发票门正确地判成悬空。）

也就是说：这条门一直在声称它看守「别把无关文件当证据」，而 M2 恰好把那个无关文件
当作证据端了出来，它一个字都没说。修法是让比较落在**名字**上而不是路径上，
并把命中列表打进失败信息：

```python
assert all(Path(hit.path).name != "notes.md" for hit in noisy), [hit.path for hit in noisy]
```

修完之后：干净绿、M2 红（就是第 5 节 M2 那一行的第四条）。
全仓 grep 同一形状（裸名 `!=` / `==` 对 `hit.path`）只有这一处，没有第二批。

**入册的规矩**：凡「某文件不该出现在结果里」的断言，必须先确认被比较的那个字段
装的是相对路径还是文件名，并当场造一次它**该红**的变异——恒真的排除式断言
比没有断言更糟，因为它让「有人守过」这句话可以一直写下去。

### 7. 真跑（真实大模型，一次请求）

门保护的是一条真实的生产接缝：`minicc/web.py:1169` 起，`/api/chat` 把
`get_evidence_index(workspace).search(message, limit=8)` 的结果拼成
`[本地检索索引]` 系统消息，而 `minicc/web.py:1170` 的 `if evidence_hits:` 意味着
**0 命中就不追加这一块**——这批门钉的正是「追加进去的每一行都是真证据」。

按生产同样的拼法对真实仓库发一次请求（`protocol=chat_completions`，key 只经
`config.describe()` 输出 `key=set`）：

| 读数 | 结果 |
| --- | --- |
| 提示里的证据块 | 8 条路径，首条 `docs/ROADMAP_TO_PRODUCT.md`（content+fresh 8.999） |
| 模型答 | `minicc/web.py` |
| 答里出现的、不在证据块中的文件路径 | 0 条 |
| 空白消息 `"   "` 的命中 | `[]` → 证据块不追加（已实测） |
| 纯 ASCII 乱码 `qzxjvbwk` | 0 命中 |
| `qzxjvbwk zzzqqq jjkk` | 2 命中——`grep -rn zzzqqq` 证实该串字面存在于 `tests/test_memory.py:229` 与 `tests/test_retrieval_eval.py:98`，**是证据不是捏造** |
| 中文 bigram「意义」 | 命中 ROADMAP，同样 grep 证实 |

一次请求不构成统计，只构成「这条接缝今天真的在把命中喂给模型」的见证。
乱码那一行是本批第二次踩同一个坑之前的量法：上一批我曾把「乱码有命中」当成捏造嫌疑，
这次先 grep 再下结论。

### 8. 边界（诚实的、可执行的）

- ① 这批门量的是**被打分的记录条数**，不是打分本身的成本。若有人把 `_score_record`
  写成每条记录再扫一遍全表（O(n²) 且不花 syscall），本批所有门照绿——这正是 M8-T45
  定义域的另一半，登记为下一批候选。
- ② `seen == records` 依赖 `search()` 按表顺序遍历。将来若换成倒排索引做候选裁剪，
  **放宽这批门是一次显式决定，不是默认**；届时合同应改成「凡含任一查询词的记录都必须在候选里」。
- ③ 真跑只有一次请求（配额 10 RPM），且模型只有 `step-3.7-flash` 一个口径。
- ④ M8-T58（父子 codec 不一致时非 ASCII `stdout_contains` 仍误判）仍未收口，状态见任务队列。

### 9. 基线

落地前（HEAD `018ee53`，上一批收口时冷跑）：**1125 passed / 363.25s / exit 0**。
本批后冷跑：**1129 passed / 311.16s / exit 0**（`-W error`、单进程、不设 `PYTHONIOENCODING` 之外的环境改动）。
两个数不可逐项相减：本批只新增 4 条测试并改了 1 条老断言，秒数差异来自机器负载。

## 第三十三批（M8-T58）：判据的裁决跟着宿主环境走，而我的第一版仪表被一句注释骗过

### 1. 这一批是上一批登记的那笔

M8-T57 收口时给命令契约的 grader 加了 `errors="replace"`——流不再被整条吞掉——
并把「父子 codec 不一致时，非 ASCII 的 `stdout_contains` 仍会误判」登记成 M8-T58。
这批就是那条，也就是第三十二批边界④里唯一还挂着编号的欠账。

### 2. 先量：这条接缝今天咬到谁了（改代码之前的读数）

| 量 | 读数 |
| --- | --- |
| `benchmarks/tasks.v2.json` 任务数 | 24：17 条 `file_contract` + 7 条 `command_contract` |
| 7 条 `command_contract` 里带 `stdout_contains` 的 | **0 条**——全部是 `{python} -m pytest -q <file>`，判据只有退出码 |
| 24 条任务里非 ASCII 的 `contains` / `stdout_contains` 值 | 0 |
| 那 7 条 fixture 的源文件里含非 ASCII 的 | 0 |
| `_run_grader` 递给 grader 的 spec | `json.dumps`，默认 `ensure_ascii=True` → 纯 ASCII，跨 codec 安全 |

所以这批不是一次「今天正在错判」的事故修复，而是一次**潜在类**的收口：咬到的是
「任何人在语料里加一条中文 marker」或「任何一台把 `PYTHONIOENCODING` 写进 profile 的机器」。
我没有去动语料（那只会让门更容易绿），改的是判据本身，并且把「当前 0 处暴露」写进边界①。

### 3. 决定性实测：同一个正确工作区，两个裁决

工作区里没有任何不确定的东西：被评分命令就是 `print('构建完成')`，
`stdout_contains` 就是那四个字。变的只有跑判分的那个进程的环境变量。

| 父进程 `PYTHONIOENCODING` | 修复前 | 修复后 |
| --- | --- | --- |
| 未设置 | passed | passed |
| `utf-8` | **failed** | passed |
| `cp936` | passed | passed |
| 三个裁决是否一致 | **False** | True |

机制：子进程的输出 codec 由 `PYTHONIOENCODING` 决定，而 grader 的文本读取用
`locale.getpreferredencoding()`——环境变量只推动其中一端，比较就错。
错的方式不是抛异常（M8-T57 已经堵掉了那种），是**把对的判成错的**：
marker 回来是乱码，`stdout_contains` 不匹配，`COMPLETE:0`。

### 4. 改了什么：一处接缝，两端同时声明

`minicc/bench_tasks.py` 的内嵌 `_COMMAND_CONTRACT_GRADER`：捕获加上
`encoding="utf-8"`，同一脚本里给子进程的 env 加上 `PYTHONIOENCODING="utf-8"`，
M8-T57 那一半（`errors="replace"`）保持不动。

**没有改的外科**：外层 `_run_grader` 的捕获仍然走 locale。理由是实测，不是省事——
marker（`MINICC_*_COMPLETE:<n>`）全 ASCII，非 ASCII 只会出现在失败分支被原样转述的
诊断文本里，所以那一段不承载裁决；改它只会把「崩溃」换成「乱码」，
反而制造 M8-T57 里那种「看起来对、其实错」的字符串。这条判断写在这里，
是为了下一个以为「这里漏了」的人不必重新量一遍。

### 5. 落地的门（`tests/test_subprocess_decoding.py`，11 条 → 16 条）

| 门 | 钉住的合同 |
| --- | --- |
| `test_a_non_ascii_command_verdict_does_not_move_with_the_parent_environment` | 同一个正确工作区在三种 parent codec 下的裁决**全等且全过**；docstring 里就是第 3 节那张实测表 |
| `test_an_embedded_grader_names_the_codec_on_both_ends` | 内嵌 grader 脚本里的 text-mode 捕获必须两端都声明 codec；带域下限断言——否则「没有违规」和「一个捕获都没看见」读起来一模一样 |
| `test_a_comment_about_the_codec_pin_does_not_satisfy_the_pin_rule` | 注释里写着 codec、代码里没有 ⇒ 判不合规；而生产 grader 注释长、赋值也在 ⇒ 仍判合规（防挖空过度把规则弄瞎） |
| `test_the_scanner_sees_an_embedded_capture_that_pins_only_its_own_reader` | 三条合成见证：只钉自己那一端 / 两端都不钉 / 两端齐 |
| `test_a_non_ascii_file_contract_verdict_is_stable_because_the_spec_travels_as_ascii` | 定义域边界：文件契约本来就环境无关，原因是 `json.dumps` 的 ASCII 运输——这条写成断言而不是叙述 |

三条 parent codec 而不是两条，是为了让门在任何语言环境上都有牙齿：
未设置那一端等于宿主 locale，那么 `utf-8` / `cp936` 里至少有一条与宿主不同，
修复前那一端必红；两端同型的门在另一台机器上就变成恒真。

### 6. 变异读数，以及被抓的是我自己的仪表

| 变异（每条一个字节级锚点，跑完还原并复验 sha256） | 六条门里的读数 |
| --- | --- |
| M1 去掉内层 `encoding="utf-8"` | 3 红：行为门、结构门、注释见证门 |
| M2 去掉 env 里的 `PYTHONIOENCODING="utf-8"` | 3 红——**第一版只有 1 红**，见第 6 节 |
| M3 回到修复前的整段形状 | 3 红 |
| 控制（未变异） | 6/6 绿 |
| M8-T57 那条 `test_a_graded_command_that_emits_undecodable_bytes_is_not_graded_as_failed` | 三条变异下全绿——诚实记录：「吞流」和「错判」是两件事，这批的门不互相覆盖，那批的也不覆盖这批 |

**M2 那一行是本批的真发现**，而且发现的不是我改的那行代码，是我新写的仪器。
第一版结构规则判断「子端声明了吗」的方式是：这段脚本文本里有没有
`PYTHONIOENCODING` 这个字面量。而我给这次修复写的注释里，正好逐字写着
`PYTHONIOENCODING=utf-8`。于是 M2（把 env 里的那个键删掉、注释留在原地）
让行为门变红、**结构门却读成合规**——一份「代码已回滚、说明书还挂着」的文件，
在它声称看守的那条规则下是干净的。

修法两层：`_code_only()` 用 `tokenize` 把注释按跨度挖空（行结构不变，
所以 `lineno` 与命中位置仍可比），规则改成只认**赋值形状**
（`PYTHONIOENCODING` 后允许 `"` `'` `]` 与空白，再跟 `=`）。同时补一条反面见证，
防止挖空过度把规则弄瞎：生产 grader 注释长、赋值也在，必须仍判合规。

**入册的规矩**：凡是「读源码文本」而不是「读 AST 节点」的门，
都必须过一次变异——把那句话从代码搬进注释。搬得动，说明门在读说明书。

### 7. 真跑（真实大模型，一次请求；外加隔壁接缝的对照）

门保护的是判分流水，而用户能看见的是模型收到的那串字符。所以真跑量的是**产品自己那条接缝**：
把父进程设成第 3 节里那个敌意环境（宿主 locale 是 cp936，环境里塞 `PYTHONIOENCODING=utf-8`），
用生产 CLI（provider、工具循环、会话落盘全真，只加 `--yolo --no-stream --max-turns 6`）
让它跑 `python -c "print('构建完成')"` 并把标准输出原样带回来：

| 读数 | 结果 |
| --- | --- |
| CLI 退出码 | 0 |
| 工具行 | `[tool 1] bash · python -c "print('构建完成')" · (exit 0, 2.4s)` |
| 工具返回给模型的正文 | `(exit 0, 2.4s)` 换行后 `构建完成` |
| 模型答 | `构建完成`（一字不差，未翻译未解释） |
| 转写里是否出现乱码（`鏋` / `瀹` / `锟`） | 否 |
| 会话记录 | `.minicc/sessions/latest.json` 含那四个字（同目录的 `.json.lock` 是 0 字节，不含正文，别把「锁文件里没有」读成丢失） |
| 用量 | `total_tokens=7483` |

一次请求不构成统计，只构成「这条接缝今天真的把完整的中文递到了模型面前」的见证。

**隔壁接缝的对照**（同一批必量的第二件事：修了一处，旁边那处是不是同一个病）：
`minicc/tools/bash.py:155` 的 `decode_process_output` 按字节捕获、再用 `[utf-8, gb18030, cp936, locale]`
的回退链解码。三种 parent codec 各跑一次真实子进程：

| 父进程 `PYTHONIOENCODING` | 子进程原始字节 | 解码结果 |
| --- | --- | --- |
| 未设置 | `b'\xb9\xb9\xbd\xa8\xcd\xea\xb3\xc9\r\n'`（GBK） | `构建完成\r\n` |
| `utf-8` | `b'\xe6\x9e\x84\xe5\xbb\xba\xe5\xae\x8c\xe6\x88\x90\r\n'` | `构建完成\r\n` |
| `cp936` | 与第一行同 | `构建完成\r\n` |

字节确实随环境变了（这正是第 3 节的机制在低一层的样子），解码串却是三条全等且正确——
所以那一处**不需要改**，这是负结果，记下来是为了省下一个人重新量一遍的时间。

顺便记一次我自己的量法错误：脚本里期望值写成 `构建完成 + '\n'`，实测全等 `False`，
而真实子进程在 Windows 下吐的是 `\r\n`。**一次 False 先怀疑判据，再怀疑被测物**——
把 `exact=` 那一列留着不是为了说明有缺陷，是为了说明数怎么错的。

### 8. 边界（诚实的、可执行的）

- ① 当前 shipped 语料 0 处暴露（7 条命令契约没有一条用 `stdout_contains`，
  fixture 全 ASCII）。这批的门的牙齿在「下一个人加一条中文 marker」之前不会咬到语料，
  它咬的是**判据形状**。
- ② 修复把「裁决随宿主环境漂移」换成了「裁决假定被评分者说 UTF-8」。
  如果被评分的是非 Python 命令、且它写 GBK 字节、且 marker 是非 ASCII，
  仍然不匹配。要真正覆盖那一形，需要字节比较或 codec 回退链，
  而那会让内嵌 grader 从「读 spec 判分」变成「猜编解码」——本批判它不值。
- ③ 结构门的域是 embedded 脚本里的 text-mode 捕获，实测 1 条；
  域外那条（父层 `_run_grader`）由第 4 节的实测显式豁免，不是没看见。
- ④ 下一批登记为 **M8-T60**（不是 T59：那个编号已被第三十一批的双通道工作占用，
   我在任务队列里登记时撞了号，改在这里而不是改那一批的标题——标题是历史，编号是账）。
   内容是：`test_a_non_ascii_worktree_path_survives_the_reader` 这类
   `skipif(_LOCALE_IS_UTF8)` 的门，在 UTF-8 机器（含 CI）上等于不存在——
   而本批已经证明不需要宿主 locale 配合就能造出不一致（显式设 codec 即可）。
   先量的数在这里（未改任何文件，用仓库自带的扫描器，不是另写一份）：
   全仓 `skipif` 门**只有 1 条**，就是这个；`minicc/` 与 `scripts/` 里 text-mode 捕获
   29 条，22 条显式钉了 UTF-8，剩下 7 条**每一条都带 `errors=`**（M8-T57 那一族的形状），
   其中生产侧 3 条：`minicc/behavior_bench.py:105`、`minicc/bench_tasks.py:229`
   （第 4 节已用实测豁免的那条）、`minicc/benchmarks.py:661`。
   所以 M8-T60 不是「扫全仓」，是把这 1 条门的牙齿从宿主手里拿回来，并给那 7 条各自一个决定。
- ⑤ M8-T61（第 9 节末尾那条墙）不在本批做，理由写在那里。

### 9. 基线，以及量基线时踩到的三个坑

落地前（HEAD `4d5afe1`，第三十二批收口时冷跑）：**1129 passed / 311.16s / exit 0**。
本批后冷跑（同一台机器，`-W error`、单进程、不改 `PYTHONIOENCODING` 之外的环境）：
**1128 passed / 6 failed / 2847.95s / exit 1**，收集总数 1134 = 1129 + 本批新增 5 条。

三个坑都记录在这里，因为每一个都能让下一次「冷跑」读出一个假数：

1. **`-W error` 必须作为 pytest 的参数，不能作为解释器的参数。** 解释器层的
   `-W error` 会让 pytest-asyncio 在 configure 阶段那条 `PytestDeprecationWarning`
   变成 INTERNALERROR（exit 3，一条测试都没跑）。第一次冷跑就是这么死的。
2. **`doc_pointers.py --check` 只对「你递给它的文档集合」负责。** 只传 ROADMAP 一份时它
   exit 1，报 `DANGLING EXEMPT ... docs/PROJECT_REVIEW_2026-09-18.md:1413 已无任何文档引用`——
   而那条豁免的引用文字在另一份文档里。`check_exempt_tables` 的 haystack 就是形参列表，
   所以同一份内容被两种量法读出两个数（M8-T44 那句话的又一次实例）。用默认集合
   （19 份文档）重跑：HEAD 干净 exit 0，HEAD+本批记录也 exit 0（evidence 900 → 924，
   `见` 标记 237 → 245，检查项 64 → 64）。
3. **这台机器当时没有内存可分配**：冷跑期间实测空闲物理内存约 0.0007GB（不到 1MB），
   机器上另有 8 个 pytest 进程（其他项目的会话）。47 分半对 5 分钟，是 9 倍的减速。

那 6 条红的归因做了单独复跑（一次一个进程，只跑这 6 条）：**5 绿 1 红**。
逐条的冷跑读数在这里，因为「都是负载」这句话必须能被核对：

| 冷跑里红的这条 | 冷跑读数 | 单独复跑 |
| --- | --- | --- |
| `test_store_with_flag_requeues_interrupted` | `assert False`，`False = any(<generator ...>)`（轮询等状态） | 绿 |
| `test_bash_output_reads_incrementally` | `assert (None is not None)`（等增量输出） | 绿 |
| `test_clean_shutdown_aborts_a_worker_that_ignores_cancellation` | `timed out waiting for worker task-1da0… to reach the parked model call` | 绿 |
| `test_worker_survives_host_crash_and_continues_long_stream` | 同一句 timeout，另一个 task id | 绿 |
| `test_shutdown_reaps_detached_worker_without_resource_warning` | `assert 'failed' == 'completed'`（worker 租约到期） | 绿 |
| `test_background_output_is_bounded` | `assert None is not None`（`tests/test_background_shell.py:111`） | **仍然红** |

五条是负载形状：全是 M8-T45 那一族「门内秒数」的墙，9 倍减速下必然塌。
第 6 条不同——它给 Python 子进程**启动并写出 20000 字节**的预算是 3.0 秒，
而第 7 节那次真实的 `python -c "print(...)"` 在同样的机器状态下花了 2.4 秒：
预算没被超过多少，但它红的信息量是零，因为这条断言**没有失败说明文字**，
而同文件隔壁那条 1.5s 的（`test_kill_shell_reaps_process_within_a_second`）有。

**因此登记 M8-T61**：把 3.0s 那条墙改成同一次运行内的比值判据（M8-T45 的口径），
并给这一族每条 `assert ... is not None` 补上「等了多久、在等什么」的文字。
本批不顺手改它——它是第二件事，而 M8-T44 已经教过不要把两件事塞进一批。

本批自己的 16 条门（含新增 5 条）在这一次慢到 47 分钟的冷跑里**全绿**：
6 条红没有一条落在 `tests/test_subprocess_decoding.py`。
也就是说，这句「全绿」是被污染的运行里唯一还站得住的部分，
而那条干净的 1129 基线不能和本批的数逐项相减——两个数之间隔着一次内存饥饿。
