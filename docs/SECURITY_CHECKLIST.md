# 安全检查清单（M2 退出标准第 3 条）

> 本清单逐条登记「人工攻击 → 防线 → 回归测试 → 手工复现要点」。每一条的
> 回归测试在当前套件里是绿的；攻击思路来自 2026-09-20 的全量审核
> （docs/AUDIT_2026-09-20.md）与其后的真实运行。防线失效时，先让对应
> 回归测试变红，再修实现——不要只改文档。

## 1. 工作区边界（workspace_roots 白名单）

- **攻击**：配置 `workspace_roots=(A,)` 后，把 agent 指向 B：四个入口——
  `switch_workspace`、`POST /api/tasks {workspace_path:B}`、
  `/api/rpc turn/start`、`/api/chat`。
- **防线**：单一 `_resolve_workspace_path()`（resolve + is_relative_to），
  四个入口共用（M2-T1）。
- **回归**：`tests/test_security_perimeter.py::test_roots_reject_outside_path`、
  `::test_roots_allow_inside_subdirectory`、`::test_all_four_entries_call_shared_resolver`。
- **手工复现**：`MINICC_WORKSPACE_ROOTS=A` 启动后对四个入口分别提交 B，
  全部返回越界错误且不创建任务；B 在 A 内部时放行。

## 2. plan 模式的写/命令越权

- **攻击**：plan 模式下让模型写文件或执行命令（含规划 DAG 节点声明 exec/bash、
  `pytest -p <模块>` 这类任意代码执行形状）。
- **防线**：plan 模式拒绝 write/exec（任务级 permission_mode 进入节点授权）；
  只读白名单对 pytest 做 argv 审查（M2-T5）。
- **回归**：`tests/test_permission_modes.py::test_plan_mode_denies_write_and_exec_but_allows_readonly`、
  `tests/test_allowlist.py::test_allowlist_overrides_missing_task_write_but_not_plan_mode`。
- **手工复现**：plan 模式提交写文件任务 → 被拒；规划节点带 bash → 节点授权
  拒绝并产生 `planner_tool_out_of_scope` 审计事件。

## 3. junction / 符号链接越界

- **攻击**：工作区内的 junction（Windows `mklink /J`，`is_symlink()` 为 False）
  指向外部目录，grep/glob/tree/file_tree 泄露外部条目。
- **防线**：枚举后逐条 `resolve().is_relative_to(workspace)` 复查（M2-T6）。
- **回归**：`tests/test_security_perimeter.py::test_junction_grep_does_not_leak`、
  `::test_junction_glob_and_tree_do_not_leak`、`::test_junction_file_tree_api_does_not_leak`、
  `::test_editor_read_still_rejects_junction_escape`。
- **手工复现**：工作区内建 junction 指向含 `secret.txt` 的外部目录后，
  四条路径均不出现该条目。

## 4. `.minicc/` 内认证/授权文件的自举提权与凭据读取

- **攻击**：`write_file('.minicc/allowlist.json')` 写入 `*` 通配获得全部
  bash 权限；`read_file('.minicc/web_token.json')` 原样返回 bearer；
  `.minicc/mcp.json` 的 headers 泄露。
- **防线**：`.minicc/` 下认证/授权文件按完整路径后缀匹配——写拒绝、读脱敏
  （M2-T2）；CLI always-allow 只记具体值不记工具级通配（M2-T3）。
- **回归**：`tests/test_security_perimeter.py::test_write_file_denied_for_minicc_auth_files`、
  `::test_read_file_denied_for_web_token_and_allowlist`、`::test_read_file_redacts_mcp_headers`。
- **手工复现**：acceptEdits 下写 allowlist.json → 被拒；读 web_token.json → 被拒。

## 5. MCP spawn 的环境清洗

- **攻击**：`.minicc/mcp.json`（工作区可写）声明的 stdio server 继承父环境，
  拿到 `MINICC_API_KEY` 与 web token。
- **防线**：spawn 环境只含 PATH + 条目显式 env，并有脱敏的 spawn 审计事件
  （M2-T7）。
- **回归**：`tests/test_security_perimeter.py::test_scrubbed_env_excludes_ambient_secrets`、
  `::test_scrubbed_env_keeps_explicit_entry_env`、`::test_spawn_audit_is_redacted`。
- **手工复现**：在父环境放置假密钥后启动 mcp server，断言子进程 environ
  不含该密钥。

## 6. Web 面的 Origin/CSRF 与 token 泄露

- **攻击**：任意网页跨站 POST `/api/tasks`（回环绑定默认无 token）；SSE
  token 走 query string 被日志原样记录。
- **防线**：状态变更方法强制 Origin 同源/回环，否则 403；日志对 path 与
  token 脱敏（M3-T1/M3-T2）。
- **回归**：`tests/test_web_security.py`（Origin 策略、token 校验、日志脱敏）。
- **手工复现**：`Origin: http://evil.example` 的 POST → 403 且不创建任务；
  访问后检查 `web-*.stdout.log` 无 token 明文。

## 7. 网络门与 SSRF

- **攻击**：`allow_network=False` 时 `pip3 install` / 双空格 `git clone` /
  `rsync` 等网络命令；webfetch 打内网/回环地址（含 DNS rebinding）。
- **防线**：argv 感知的网络门（M3-T4）+ 解析一次后 IP 钉扎、逐跳重解析
  校验（M3-T3）。
- **回归**：`tests/test_network_gate.py`（含 pip3 表驱动）、
  `tests/test_webfetch.py::test_ssrf_guard_rejects_loopback_by_default`。
- **手工复现**：不开 `allow_network` 提交网络命令 → 全部拦截；webfetch
  指向 `http://127.0.0.1` → 默认拒绝连接。

## 8. 配置劫持

- **攻击**：Windows 环境里一个 `MODEL=` 环境变量劫持配置文件（大小写
  不敏感的 `os.environ` 查找）；`.env` 解析了但不生效。
- **防线**：`pick()` 按 config 键名精确匹配 + `.env` 显式导出（M2-T8）。
- **回归**：`tests/test_security_perimeter.py::test_stray_uppercase_env_does_not_hijack_config`、
  `::test_env_file_exports_minicc_toggles`。
- **手工复现**：环境里放 `MODEL=attacker` 后启动，配置文件的 model 仍生效。
