# 变更日志

> 全局索引：[INDEX.md](INDEX.md)。

## v0.2.0（2026-11-10 合并到 `main`）

本版本记录的是**一次完整合流**：从 2026-09-20 启动到 2026-11-10 本日，所有并行工作树/lane/集成分支被收敛到同一条 `main`，并以一条能红能绿的 CI 线守护每一次推送。

### 里程碑落地（M1 → M8）

| 里程碑 | 主题 | 落地重点 |
| --- | --- | --- |
| M1 | 核心链路可信 | Streaming delta 拼接不丢字符；`finish_reason` 非终态不交付；恢复保护必须自增且终止；`scripts/reliability_probe.py` 退出码 0 守护。 |
| M2 | 权限模型 / 工作区边界 | allowlist 的 `fnmatch` 极权口子关闭；`read_file` 对 `.minicc/web_token.json` 脱敏；`/v1/messages` 非回环 Origin 403；`permissions.json` 解析失败不再放行。 |
| M3 | 凭据 / 网络 / 进程 | `.minicc/worker/` 明文 key dump 清理；Origin/CSRF 防线接入；强杀 worker 后可 auto-resume；`sk-` 扫描零命中。 |
| M4 | 证据链 / 评测可信度 | 行为套件 + `--suite v2` 实测；`benchmarks/tasks.v2.json` 任务数 ≥24；A/B 门 dev/prod 分流；`grading_coverage` 自报口径（`declared`/`executed`）；nightly 绝对门 floor 值两侧一致。 |
| M5 | MCP 桥加固 | `_content_to_tool_result` 截断 6000；id 容错；reader 死后 <1s 失败；`mcp__` 工具 CLI/Web 同列。 |
| M6 | 有界可写委派 + 后台执行 | 子代理默认 acceptEdits；父会话协议校验；`BudgetExceeded` 硬停；后台 shell 可取消且无残留进程。 |
| M7 | 平台化：Hooks / Slash / 审批 | hooks 四事件集成测试；CLI/Web 双端 `.minicc/commands/<name>.md` 展开；Web 真实审批从请求到落库；断网 composer 可恢复。 |
| M8 | 记忆 / Fork / 插件 API / 产物 | 快照验证只读 digest 校验；会话 fork 可 `--resume`；`docs/PLUGIN_API.md` 示例原样跑通；`docs/` + `docs/ROADMAP_TO_PRODUCT.md` 24000 行账本锁住一切成果。 |

### 本轮合流关键落地（批次 M8-T686 → M8-T770）

- `minicc --doctor`、`--doctor-strict`、`--stats`、`/doctor`（REPL）、`/api/doctor`、`minicc --setup`、`minicc --version --json` 全部交付（`minicc/doctor.py`、`minicc/setup.py`、`minicc/stats.py`、`minicc/main.py`）。
- 首小时手册、运维手册、互联门户、服务面运维手册合流完成：`docs/FIRST_HOUR.md`、`docs/OPERATIONS.md`、`docs/INDEX.md`、`docs/SERVICE_PLANE_OPERATOR.md`；入口 `README.md`、`docs/INDEX.md`。
- 服务面按 P1..P5 分阶段落地（`minicc-cloud/minicc-cloud-registry` / `minicc-cloud-config` / `minicc-cloud-inspector` / `minicc-cloud-tasks` / `minicc-cloud-gateway` / `minicc-cloud-bridge`）；`docs/SERVICE_PLANE_PLAN.md` 规划、`docs/SERVICE_PLANE_OPERATOR.md` 经验证的运维手册、`docs/SERVICE_PLANE_PLAN.md` 与 `minicc-cloud/README.md` 是日常入口。
- 文档指针门（`scripts/doc_pointers.py`）、宽面名册门（`tests/fence_rosters/wide.txt`）、M6-4 P95 退化读者门（`tests/test_the_m6_4_degradation_standard_has_a_reader.py`）、快照 deny-once 门（`tests/test_the_snapshot_deny_question_is_asked_once_per_capture.py`）、句柄门（`tests/test_the_file_handles_are_closed.py`）等 20 余道"接手并轨"门全部迁入本仓。
- REPL `/doctor` 与 `cost`/`doctor` 保留字（`minicc/commands.py::RESERVED_COMMAND_NAMES`）确保自定义 `commands/*.md` 无法遮蔽内置命令；`/quit` 别名已纳入名册（门：`tests/test_readme_interaction_commands_match_the_reserved_roster.py`）。
- 索引与文档清单门：`tests/test_docs_index_enumerates_every_docs_md.py`（INDEX 必须点名每篇 docs *.md）、`tests/fence_rosters/wide.txt`（docs 见证测试的入册清单）。
- 新 API 旗标总表与贡献者流程：`docs/CLI_REFERENCE.md`、`docs/CONTRIBUTING.md`、根级 `SECURITY.md`、`.github/PULL_REQUEST_TEMPLATE.md`、`docs/SERVICE_PLANE_GATEWAY.md`。
- 模块级单测覆盖补齐：`minicc/atomic_file.py`（8 条）、`minicc/static_assets.py`（10 条）、四个"一事一源"叶子模块（19 条）、`gitprobe`/`logging_setup`（21 条）、`stream_merge`/`schemas`（30 条）、`tools/fs.py` 守卫规则（35 条）、`check_commands`（16 条）、`llm/base`/`agent/test_selection`（22 条）。
- 服务面第七个模块 `minicc-cloud-insights`（8087，只读聚合洞察：总数 exact、分状态 capped、audit 行数 capped）；网关 `/api/insights/**` 路由 + 独立 `/fallback/insights`；8083 因本机已被其他项目占用而挪到 8087。`minicc-cloud-tasks` 默认读 `tasks.sqlite3`（Python 引擎唯一文件名，M8-T769 漂移修）。

### 目录与产物事实

- 产物：`minicc`、`minicc-web`
- 语言：Python ≥ 3.11（`pyproject.toml`）；前端：React 19 + Vite 6（`package.json`）
- 工作树：本日 `main` 相较 `42be4e3` 多出 ~350 条提交；`docs/` 新增 `docs/OPERATIONS.md`、`docs/SERVICE_PLANE_OPERATOR.md`、`docs/ONE_FACT_ONE_HOME.md` 等方法论文章。
- 入口文档：`README.md`、`docs/INDEX.md`、`docs/CLI_REFERENCE.md`、`docs/CONTRIBUTING.md`、`docs/ONE_FACT_ONE_HOME.md`、`docs/SERVICE_PLANE_PLAN.md`、`docs/FIRST_HOUR.md`、根级 `SECURITY.md`。

### 已知问题（记录在案）

- `pip install` 需访问 `[dev]` extra 才会在本机拉齐 `openai`；`test_packaging.py::test_installed_console_scripts_run_from_a_real_install` 仅在 CI 中以 `pip install -e ".[dev]"` 的系统解释器红绿可证，Windows 本机因全局 Python 缺少 `openai` 长期红而在 CI 绿。
- Nightly eval 始终 skipped，真实模型只进 nightly。
- 跨 Web 重启的 SSE 镜像尚未实现（`docs/GAP_ANALYSIS_AND_ROADMAP.md` 里有记录）。

---

版本号策略：`minicc/__init__.py::__version__` 是唯一版本号家（pyproject、vscode-extension、embed 字符串全部对齐）。任何改动同时改三处会被 CI 的 `pyproject` 门与 `test_project_config.py` 拦下。

制作：2026-11-10 合并落地。

---

# 2026-11-12（并轨归并与 CI 红修轮）

- **测试套件红线逐一对账（M8-T818..T836）**：备份线合入（M8-T811）留下的预存红逐个处理；`tests/test_pricing.py` 完整套件（34 绿）；`tests/test_mcp.py`、`tests/test_webauth.py`、`tests/test_worktree.py`、`tests/test_workspaces.py`、`tests/test_trace.py`、`tests/test_snapshots.py` 新增压缩（纯函数、零网络）；`tests/test_result_row_census.py` 改按 M8-T118 退役计数（`repeated_tool_calls`/`tool_repeat_rate` 的死名流拷被移除）；`tests/test_rubric_shape.py` 改按当前拒绝理由/双主读取结构对账（21 绿）；`tests/test_grader_clock_attribution.py` 收窄为当前设计的 5 条（备份线 TIMEOUT 归因子系统从未落地）；`tests/test_cli_i18n.py` 随并轨否决的 i18n 双语框架一并删除；`tests/test_impacted_tests.py::test_every_module_in_the_package_imports` 的根因是死包 `minicc/repl/`（`__init__.py` import 了 git 全史从未存在的 `repl.py`）——整个死包已删除。
- **真实大模型端到端跑通**：`.env`（不入库、已 gitignore）指向 wkapi.pro/v1 的 `gpt-6-sol`（reasoning_effort=max，responses 协议）；`--doctor` 6 ok / agent CLI 跑通 / web 聊天路径可用；`minicc.webserver` 导入从 ~50-70s 降到 **1.6s**（惰性 import openai SDK）。
- **网关与 service plane**：顶层重复 `spring:` 已合并为单一树（SnakeYAML 报 `found duplicate key spring` → 此前 gateway 上下文根本加载不了）；gateway 测试离线隔离（`test/resources/application.properties`）；CacheKeys.forService 一元化 + fanout invalidate（RabbitMQ）；M8-T826（并行会话）补发布者 + ShippedCacheKeysAgreeTest；M8-T822/T823/T824/T836 网关门全绿（mvn 93→101 个测试通过）。
- **前端**：mobile 阅读宽度契约修正（≤640px 不再把气泡钉 75%，web smoke mobile 步骤通过）；React 19 主 workbench 保留玻璃态视觉语言（M8-T814）与文本对比度门 ≥4.5。
- **游戏 smoke 去 flake（M8-T828/T830）**：`impacts` 改为轮询等待而非固定 sleep；timeStop 僵尸改静止（速度 1.2 的竞争帧让 impacts 丢失，CI 红）；`npm run test:web` 现在四件全绿（timeline/product path/desktop/mobile）。

- 新增样张截图与 Playwright：frontend_optimization_smoke、game_upgrade_smoke、web_smoke 三件套在本机全绿。


- **任务库按会话读取提速（M8-T837）**：`list_by_session` 不再拉全表逐行 `json.loads`；改 `session_id` 的 SQL 级过滤（JSON1），坏行回退原语义。本机临时库 800 条快照：~58ms → ~36ms。

- **新增 docs/PERFORMANCE.md（性能与测量索引）**：汇总本主线有实测数据的优化（import 1.61s、SQLite JSON1、impact BFS、网关缓存、前端对比度门与对比度 ≥4.5 契约、内容寻址产物），以及给后人的三个明确"未做"（cached route 下游契约、FTS 命中率、JSON1 缺失环境的回退臂）。

- **Python CI 全绿（0 failed）**：M8-T832 的 53 failed 预存红全部对账修复；补丁集中在并轨备份线遗留的 i18n 双语、TIMEOUT 归因、repeated_tool_calls/tool_repeat_rate、rubric/census/attribution 等对账，加上本主线的 `minicc/repl` 死包删除。ubuntu 5540 passed / windows success（run `43244566867`）。
- **`minicc/task_store.py::list_by_session`** 改 JSON1 SQL 级过滤（800 快照临时库 ~58ms → ~36ms）；整体套件收集从 ~70s 降至 ~20s（`minicc.webserver` 导入已降至 ~1.61s）。
- **`minicc/repl/` 死包删除**（`__init__.py` import 从未存在的 repl.py；CI 下限普查直播那里被拦下）。
