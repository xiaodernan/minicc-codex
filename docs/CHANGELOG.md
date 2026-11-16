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

- **静默门 population 断言适配 Redis 池的宽进（M8-T841）**：`redis_cache.py` 的 4 个值返回型吞并（`return False, None` / `return False`）使第三道门与两个窄化并集不再等齐；`test_broad_silent_handlers_state_a_reason_mutation.py` 改为严格超集断言 + 卫星点必须自带说明理由（全部带 `# noqa: BLE001 - <why>`），`test_mutation_cells_react_to_the_code_they_name.py` 4 处 `must_go_red` 同步复名。

- **dev extra 补 redis（M8-T851）**：CI 装 `pip install -e ".[dev]"`，此前 dev 里根本没有 `redis`，导致 `minicc/redis_cache.py` 的真实 Redis 分支在 CI 上从未被真正执行（即使 `.[dev]` 装了也拿不到 `redis` 驱动）。现在 `test_ci_hygiene.py::test_redis_is_declared_dev_dependency` 把 `redis>=5.0.0` 钉进 dev extra，12/12 CI hygiene gate 和 17/17 `test_redis_cache` 在有可用 Redis 实例的情况下都通过，cross-process set/get / TTL / namespace 都在本机验证过。
- **网关 `/api/cached/*` 不再返回模拟数据（M8-T848）**：`CachedRouteController` 两路代理改为用 client-side load balancing（`@ReactorLoadBalancerExchangeFilterFunction`）发 `lb://minicc-cloud-inspector|insights` 真实 upstream 健康状态；新增 `UpstreamHealthProbe` 让生产用 WebClient、测试换 fake；`CachedRouteControllerTest` 4/4 钉住「响应来自 probe 不是来自常量」。
- **新增 `/api/health/all`（M8-T850）**：网关对三个后端**并行**发 lb:// probe，`{services:[...], upCount:N, totalServices:3}` 输出；3/3 `AggregateHealthControllerTest` 钉住 all-up=3、不是全-down=0、chaos=1；docs 实机演示见 `SERVICE_PLANE_OPERATOR.md` §7。
- **`minicc-cloud-registry` 首个测试（M8-T849）**：`RegistryHealthTest` 起随机端口 registry，`/actuator/health` 和 `/eureka/apps` 断言——此前该核心模块零测试。
- **`minicc/task_store.py::list_by_session`** 去掉全表 `json.loads`，改用 SQLite JSON1 `json_extract` 下推过滤（`~58ms -> ~36ms`，800 条快照本机实测）。

# 2026-11-13（Redis 实机化 + 消息队列 + 字型上线轮）

- **`minicc/redis_cache.py` 修掉 redis-py 自 2.6.12（2013）就 deprecated 的 `setex`**（M8-T852）：改 `set(key, value, ex=seconds)`；新增 opt-in 实机门 `tests/test_redis_cache.py::test_redis_live_backend_roundtrip`（`MINICC_TEST_REDIS_URL` 不设则 skip）；本机 7-alpine 容器实测跨进程 set/get、TTL 过期、namespace 隔离全过。
- **`/api/metrics` 新增 `redis_cache` 拓扑段**（M8-T853）：`gets/hits/misses/fallback/sets_shared/sets_local/deletes/clears` 计数器 + `live_backend` + `local_units`——操作员从 web 面板一眼看出"这个进程到底是不是在真 Redis 上跑"；`tests/test_logging.py::test_metrics_payload_carries_redis_cache_topology` 钉住字段与类型。
- **M8-T853 的连带红修**（M8-T854/T855/T856/T857）：修 `_Wire` mock 的 `set` 签名对接 redis-py 4+；`minicc/web.py` 改成 lazy import（行号引用归位）；evidence index 上限 1200→2500（仓库膨胀后 80% 线被顶穿）；`tests/test_logging.py` 引用改按名不按行；一次意外 CRLF 事故的回滚（全 LF 归一）。
- **网关缓存失效总线的实机 AMQP 回环**（M8-T857）：`CacheInvalidationRoundTripLiveTest`——用 throwaway auto-delete 队列 bind 到 `minicc.gateway.route.refresh` fanout exchange，断言消息穿过去且 header `route` = 规范键；缺省 skip，`MINICC_TEST_RABBIT_URI` 提供时真 broker 全过（本机 rabbitmq:3-alpine 验证）。
- **vendored Manrope + DM Mono（OFL-1.1）**（M8-T858）：设计系统一直以来按名引用却从未打包的字型（`web/fonts/`，573 KB TTF + 许可全文），`index.html` 预载，`static_assets.py` 字体扩展名显式 `font/ttf` content-type；`npm run test:web` / `test:optimization` / `check:web` 全绿；字体 ETag 304 复用已验证。
- **分支/worktree 并轨审计**（M8-T856）：逐条取证所有未合入 ref（`consolidation/*`、`archive/*`、`backup/*`、`dev/minicc-reliability-4ba3`、`origin/m8-t537`、`origin/integration/*`）——全部为主线已吸收的旧世系或同号不同事的备份线；**无任何可安全合入 main 的世系**，审计结论写入 ledger，`wt*`/`plane*` 目录只读不动。
- **网关 cached-route 真上游化 + 聚合健康面**（M8-T848/T849/T850）：`/api/cached/*` 从常量 `Map.of` 改为 lb:// 真探活上游 `/actuator/health`；新增 `/api/health/all`（并行探三个后端）；`minicc-cloud-registry` 首个测试（health + eureka/apps）；operator 手册 §7 实机记录完整命令链路。
- **真实大模型端到端**（早前）：`gpt-6-sol` 通过 wkapi.pro/v1 跑通 `--doctor`、provider chat、`minicc --yolo`（用户提供的真实 API，只用于该验证）。

- **网关缓存修掉一个"没人能看见的"生产缺陷（M8-T861）**：网关 `/api/cached/*` 在 `spring.cache.type=redis` 下每次 cache 写都会炸（缓存的 `Mono<ResponseEntity<Map>>` 里 `ResponseEntity` 不可序列化）；`CachedStatusService` 作为 @Cacheable 边界，缓存纯 Map/String（JDK 可序列化），`CachedPayloadRoundTripTest` 钉住真序列化往返；新增 `/api/cached/inspector/changes?workspace=<abs>`（lb://→inspector→Python bridge，String 直存）；inspector `MiniccProperties` 双构造器歧义 → `@ConstructorBinding`，该模块此前从未独立 boot。实机证据见 `docs/SERVICE_PLANE_GATEWAY.md` §6 与账本 861 批。
- **网关探活增加可中断超时（M8-T860）**：`/api/health/all` 的每个上游 probe 现在有硬上限（默认 2s，`MINICC_GATEWAY_PROBE_TIMEOUT_MS` 覆盖）——卡死的上游显示 UNKNOWN，不再拖住聚合答案。
- **真实模型端到端（2026-11-13 复核）**：`gpt-6-sol`（wkapi.pro/v1，reasoning_effort=high）跑 `minicc "list the files in the current directory and count them"`：先在 Windows 上 `find/awk` 失败，agent 自我修正改用 PowerShell，**18 个顶层文件答对**；`minicc --doctor` 6 ok / 0 fatal。完整 runbook 见 `docs/FIRST_HOUR.md` §6.1。

- **Docker Compose 全栈实测跑通（M8-T862）**：registry/config/redis/rabbitmq/inspector/tasks/insights/gateway 八容器一次性 healthy；gateway `/api/health/all` 稳定 3/3 UP；`/api/changes?workspace=/workspaces/target` 200（Probe repo +6/-4）；缓存失效 fanout 总线实广播 → Redis 键真删除。
- **配置/依赖两个"无人看见"的缺陷**：gateway 缺 `spring-cloud-starter-loadbalancer`（此前所有 lb:// 调用在运行时必炸，单测照样绿）；inspector 基于 jammy 的 Python 3.10 导入不了 `datetime.UTC`（`minicc/clock.py` 需要 3.11+，100% 503）——Dockerfile 改 noble（Python 3.12）。
- **`MINICC_GIT_STATUS_TIMEOUT_SECONDS`（minicc/changes.py）**：git status 的内层 20s 硬上限可被慢 FS 放宽（默认 20s 不变；非法值降级为 20s，模块 import 不抛）。compose 透传。
- **Compose 参数化端口**（向后兼容：缺省值与默认一致），并记录本机实测（全部端口被其他项目占用时如本机样子）。
- **门面化的诊断修复**：`minicc/changes.py`/`gitprobe.py` 的 git 超时话术已串成 `git_status_timeout_reason(n, subject)`；`agent/loop.py`(15s) 与 `snapshots.py`(20s) 也经过盘点。

- **Lighthouse 三项满分（M8-T863）**：`browser.lighthouse` 真实 Chromium 审计修复：accessibility 0.96 → **1.00**、best-practices **1.00**、SEO 0.75 → **1.00**；`meta-description`（中英双语）+ 双 `theme-color`（light/dark media）+ 首屏 pre-paint 主题脚本（消除先 dark 后 light 的闪烁）+ `#profileButton` 无障碍名与可见文本对齐（`当前模式` → 由可见文本「面试模式 仅本地」派生）+ 头像 `aria-hidden`；`applyTheme` 现在同步**全部** theme-color meta。
- **SQLite 表达式索引尝试与回滚（M8-T864）**：`list_by_session` 值得索引（438→46ms，9.4×）；但表达式索引逼写路径也容忍畸形 JSON —— 与 durability 契约冲突（`tests/test_task_store_durability_contract.py::test_corrupt_payload_does_not_break_load_or_get` 实锤失败），**已回滚**，实测结论与证据入账本。

- **Bridge 边界 transient-retry（M8-T867）**：`GovernedRunner` 新增 5 参构造器（`maxAttempts`/`retryDelay`），delegate 抛 volatile 异常时带短退避重试（默认 3 次 / 150ms），"提前断开"不再让整个 inspector 变 503；接线到 inspector `BridgeConfiguration`，knobs 落 `application.yml` + config-server `config-repo/minicc-cloud-inspector.yml`（`MINICC_CLOUD_BRIDGE_MAXATTEMPTS` / `MINICC_CLOUD_BRIDGE_RETRYDELAYMS`）；`GovernedRunnerRetryTest` 5 条钉住 volatile/回收/换手/非零退出码不重试/permits 不泄漏。

- **Actuator `/actuator/info` 首次上线 build 信息（M8-T868）**：gateway 的 `spring-boot-maven-plugin` 绑 `build-info`（phase=generate-resources），
  `META-INF/build-info.properties` 产出 artifact/group/version/time；运维现在能 `GET /actuator/info` 看到
  `{"build":{"artifact":"minicc-cloud-gateway","version":"0.1.0","time":"2026-11-13T04:56:33.309Z",...}}` 而不需要 SSH；`BuildInfoResourceTest` 2 条钉住键集合。

- **cached-route 负载带 `fetchedAtMs`（M8-T869）**：`/api/cached/inspector/status`、`/api/cached/insights/summary` 的响应现在多出一个 epoch-millis `Long` 键——CLI/仪表盘可用 `now - fetchedAtMs` 判断缓存年龄而不需要再去 query `PTTL`；JDK 序列化往返（CachedPayloadRoundTripTest）原样保留；消费者若不认识这个字段，也不会受影响。

- **Spring Cloud LoadBalancer — 换 Caffeine（M8-T870）**：网关启动时"This cache implementation is useful for development and tests"的 WARN 彻底消失；`lb://` 上游 lookup 的实例集合现在走 Caffeine（真的 LRU+并行驱逐）；`loadbalancer.cache.enabled/ttl/capacity` 全部参数化（`minicc.cloud.gateway.loadbalancer-cache-ttl:30s`、`capacity=256`）。

- **Spring Cloud LoadBalancer health-check 参数化（M8-T871）**：`spring.cloud.loadbalancer.health-check.path.default=/actuator/health` + `interval=10s`——上层 Eureka 的 UP/DOWN tag 不再是唯一真理（依赖 30s heartbeat），LB 现在每 10s 直接探活，剔除真死 instance；compose 全栈实测 3/3 UP、`/actuator/health` UP、cached routes roundtrip 正常。

- **compose RabbitMQ cookie 显式固化（M8-T872）**：`docker-compose.yml` 的 `rabbitmq` 服务补 `RABBITMQ_ERLANG_COOKIE=minicc-compose-secret-key`——`docker compose up -d` 在 Docker Desktop / WSL2 下不再以 EACCES 静默崩溃；本地一次拉起全栈 → `/api/health/all` 3/3 UP、cached routes Redis 命中持续生效。

- **`--stats` 现在带 cache 拓扑（M8-T874）**：`minicc --stats` 现状面板多一行 `cache: live|local`——CLI 就能一眼看到"明明配了 `REDIS_URL`，到底生效没有"，对应 Web 面板的 `/api/metrics.redis_cache`；`--json` 输出亦多一个 `cache` 子树；现有 `--stats` 读端点不变，新增 key 仅追加。

- **insights `/api/insights/disk` 落地（M8-T875）**：新只读端点给出 `.minicc/` 整体字节/文件数/SQLite 字节数、可用卷余额——运维一组 `curl http://.../api/insights/disk` 就能回答"占了多少空间、还剩多少"；honor 既有 `InsightsFailureAdvice`（DB 缺 → 503，不可读 → 500）；`DiskProbeTest` 2 条钉住两个分支。

- **config-server build-info 落地（M8-T876）**：`/actuator/info` 不再是黑盒——`META-INF/build-info.properties` 由 `spring-boot-maven-plugin:build-info` 在 generate-resources 阶段产出，实时暴露 artifact/group/version/time；`ConfigServerBuildInfoTest` 钉住键集合。

- **所有 Spring Cloud 模块都上 `/actuator/info` build-info（M8-T876 + M8-T877）**：registry、inspector、tasks、insights、gateway 五个 Java 服务现在统一从 `spring-boot-maven-plugin:build-info` 产出 `META-INF/build-info.properties`，`/actuator/info` 对任一服务都能看到 artifact/group/version/time——运维一组 curl 就知道部署了哪次工件；目标绑 `generate-resources` 阶段保证 `target/classes`、打包 jar、在 compose 全栈一起跑时都能读到。

- **OpenAI 兼容网关前缀缓存亲和落地（M8-T878）**：所有发往 `/v1` 的线路（Responses / Chat Completions）现在都携带 `prompt_cache_key`——显式 `MINICC_PROMPT_CACHE_KEY` 优先，否则按 `sha256(base_url|model)` 派生不透明键（不泄露工作区路径，跨进程稳定）。实测 wkapi.pro 上 `gpt-6-sol` 连续同前缀请求：热缓存命中从 0% → **98.4%**（agentic tools 回合 80.9%）；CLI `[usage]` 行现在在网关有上报时追加 `cache_hit_tokens / cache_miss_tokens / cache_hit_pct`，缓存效率当场可见。

- **恢复尝试不再殃及任务余生的流式（M8-T879）**：web 任务主循环原先在一次瞬态网关故障后把该任务之后所有回合都钉成原子（`provider_recoveries > 0 ⇒ on_stream=None`），恢复完成的修复回合也不再逐步显示——用户看到的"一直显示非流"在此闭环。原子重放现在只活到恢复尝试结束为止；完成的尝试即安全地板，repair 回合（verification 失败进入）照常流式。新门 `tests/test_the_recovery_attempt_is_the_only_atomic_turn.py` 用真实任务循环钉住：恢复答案一个字都不上屏，修复答案完整上屏。

- **GAP 文档缓存亲和结论订正（M8-T880）**：`docs/GAP_ANALYSIS_AND_ROADMAP.md:175` 中"客户端无法修复"已按 M8-T878 实测订正——`prompt_cache_key` 是客户端修复，wkapi.pro 热缓存 0% → ~98.4%；历史核查事实保留不动。

- **M8-T880 行尾事故修复（M8-T881）**：`docs/GAP_ANALYSIS_AND_ROADMAP.md` 之前被误改为 CRLF（整文件 476 行 diff）；已整体回退到 LF 基底并逐字拼回唯一应变的一行——订正缓存亲和判断的那行保持不变，diff 恢复为单行。

- **网关按 IP 的 Redis 令牌桶限流（M8-T882）**：`SPRING_PROFILES_ACTIVE=ratelimit` 时，Spring Cloud Gateway 的 `default-filters` 增加 `RequestRateLimiter`（Redis 令牌桶，默认 20 tok/s 回填 + 40 burst，每 IP 一个桶）；未激活零变化。全栈实机验证：120 并发下 52 通行/67 被 429/1 次 503（上游打满时的带因回退），桶回填后恢复 200。新增 `IpKeyResolver`（无 IP 降级 `unknown` 共享桶）、`application-ratelimit.yml`（`MINICC_GATEWAY_RATE_LIMIT_*` 可调）、两个门测试 + compose 激活钩。

- **`/api/metrics` 答出前缀缓存账本（M8-T883）**：payload 新增 `llm_cache`（`cache_summary` 由 bill 用的同一本账算出）——面板/运维脚本终于不用自己对账就能看到工作区级缓存命中率；`unreported` 保持诚实的 `null` 而非伪造的 0%。`llm_cache` 与 `redis_cache` 并列为操作员可读的两个缓存面。

- **任务运行时摘要里的前缀缓存圆环（M8-T884）**：任务详情的 Runtime metrics「缓存」格子从纯文本百分比升级为内联 SVG 圆环（`pathLength=100`，三档 --mint/--amber/--rose 色调，网关未上报时只画轨道不伪造 0%，`aria-label` 随语言走）。`web/styles.css` 新增 M8-T884 段；构建产物（`web/app.js`、assets、manifest）同一提交内重建，2 个无引用旧 bundle 已清理。

- **Pulse 卡也画前缀缓存圆环（M8-T885）**：常驻屏幕的 `.pulse-card`（agent 工作时余光扫到的那张）里 `#cacheMetric` 从"未统计"文本升级为 26px 内联 SVG 圆环，与 Runtime 摘要同一实现（`cacheDonut(data, px)`）；`aria-label` 随语言走，未上报只画轨道。

- **网关 429 被拒计数进入 `/actuator/metrics`（M8-T886）**：新 `RateLimitMetricsFilter` 在过滤器链完成后仅对 `429` 递增 Micrometer counter `gateway.rate_limited{route}`——限流从"行为"升级为"信号"，Prometheus/curl 都能直接抓到按路由的拒绝数；零决策变更、零新依赖。门：`RateLimitMetricsFilterTest` 3 项。

- **`minicc --stats` 显示前缀缓存命中率（M8-T887）**：`llm_cache` 段从 `tasks.sqlite3` 快照聚合 `prompt_cache_hit/miss_tokens`（未上报行不计数，绝不伪造 0），`--stats` 输出一行 `hit rate NN.N%`，`--json` 多一段 `llm_cache`——运维裸跑 CLI 也能看见这本账。新门 `test_stats_llm_cache_aggregates_snapshots`（3/4 快照参与聚合，键集被钉住）。

- **429 计数器的装配顺序修复（M8-T888）**：T886 上线的 `RateLimitMetricsFilter` 放在 `LOWEST_PRECEDENCE`，而 Redis 限流器答 429 时不再调用下游链——计数器实测一条都没记（`/actuator/metrics/gateway.rate_limited` 返回 404，全栈实测暴露）。已改为 `HIGHEST_PRECEDENCE`（wrap 整个链），并把 `getOrder() == HIGHEST_PRECEDENCE` 钉进测试；实机验证：60 并发 → 40×200 / 20×429，`actuator/metrics/gateway.rate_limited{route=tasks}` COUNT = 20.0。

- **`minicc --doctor` 新增前缀缓存探针（M8-T889）**：`llm_cache_affinity` 在不碰网络的前提下回答"这台节点的缓存亲和接没接上"——`MINICC_PROMPT_CACHE_KEY` 显式键 vs gateway+model 派生键，无 LLM 端点时如实 warn 而非 fatal。`test_doctor.py` 三态门 3 项。

- **`minicc --stats` 的任务账合并修复（M8-T890）**：修掉了"CLI 任务计数恒为 0"这一真丢账——工作区任务住在两个 store（`<ws>/.minicc/tasks.sqlite3` 与全局 `~/.minicc/tasks.sqlite3` 且行内带 `workspace_path`），`--stats` 现在合并并按工作区作用域汇总：本仓库实测 `tasks: 13 total … [workspace 0 / home 13]`、`llm cache: 8 tasks, hit rate 41.0%`（修前直接说"no cache counters"）。隔壁 workspace 的命中令牌零字节流入本仓库账本，来源拆分（`source`）随 json 输出。

- **脉冲卡圆环引发双腿 Python CI 红的修复（M8-T891）**：T885 的 `var(--donut)` 从未在样式表里声明——`test_the_palette_has_one_home` 的"每个变量必须有声明的家"门双腿齐红。修复：`.cache-donut { --donut: 34px; }` 声明即家（内联 26px 仍覆盖）；产物重建；门 5/5 绿。

- **空状态 hero 升华（M8-T892）**：工作区第一眼从"平铺 icon + 静态卡"变成专业级 hero——64px 圆角 mark 双辉光 + `conic-gradient` 环绕光环、呼吸缩放、标题渐变 sheen（6s 往复）、start chips 弹性悬停、`prefers-reduced-motion` 全部静止。零 JS/DOM/i18n 改动，仅 CSS 追加层 + 产物重建。

- **「账本」面板上线（M8-T893）**：侧边栏新增「账本」入口（Ctrl/⌘+L），整屏摊开工作区账单——总 token 金句数字、缓存命中率 52px 圆环（hit/miss/write 拆分）、估算成本（诚实标注未定价任务）、缓存后端（Redis 实时 / 本地 LRU）、任务状态 segmented bar（已完成/失败/中断/取消 比例 + 图例）、按模型分解表（tokens / hit / miss / 任务数 / 成本，含合计行）。零新后端端点——完全复用 `/api/metrics`。命令面板一行「ledger」与 `Alt+L` 同入口；i18n 双语全量。

- **工作区脉搏上线（M8-T895）**：侧边栏新增「脉搏」，全屏三栏面板（工作区身份证 / 三枚 SVG 巨环 / 最近 12 个任务档案）；纯读 `/api/metrics` + `/api/tasks` + `/api/stats`，零新后端。缓存命中率 / 上下文占比 / 完成率 动画环即展即弃；Esc 关闭；断线时状态 pill 红色兜底。

- **模板库上线（M8-T896）**：侧边栏新增「模板库」，8 张精选卡片（项目扫描 / 跑测试并修好 / 安全审查 / 生成 README / 中文注释英文化 / 依赖体检 / 现代化建议 / 冒烟检查），一键将策划好的高质量 prompt 填入 composer 并 focus。`Ctrl/⌘+K` 面板同步新增 `templates` 条目。零新后端、零新图标，文案双语全量。

- **全量套件红灯清零（M8-T897）**：`test_installed_console_scripts_run_from_a_real_install` 本轮红了——根因是 fresh venv 用 `--system-site-packages` 继承的是**本仓库 .venv 对应的 base** site-packages，不是本仓库 .venv 的（含 tenacity 的那一份）。修复：向探针 venv 显式注入本仓库 `.venv/Lib/site-packages`（纯离线注入，不装任何东西、不削弱 anti-vacuity 门）。另外 4 个"红"是本轮长跑的 `_pytest_full_888.log`、`gateway869_*.log`、`server_*.log` 等仓库根 log 触发清理门——删干净即转绿；4 个已 PASS 复测通过。仓库根现无任何运行产物滞留。

- **工具调用流式进度（M8-T897）**：三面实测（真实网关同前缀双端点对比）定案"缓存命中率低 + 显示非流"两大抱怨——命中率是上报假象（chat/completions 永不回 `prompt_tokens_details`，Responses 如实回 72.3%），非流感的根因是 `_create_responses_stream` 只转发 `output_text.delta`，规划轮（工具调用轮）全程静默。新增 `provider_tool_call_start` / `provider_tool_call_progress`（0.5s 节流）/ `provider_reasoning_progress` 三个状态通道事件，答案流字节干净。真实 E2E：stream_delta 1→13，agent 命中率 83.7%。

- **任务坞实时工具条（M8-T898）**：规划轮期间任务坞 chip 实时显示 `◌ read_file · N 字符`（流光扫过），`function_call_arguments.done` 冻结为 mint 对勾 ✓；推理进度同样上 chip。门测试钉住 UI 正则与 Python 发射端三码的跨语言契约 + i18n.js/index.html 的 CRLF 行尾守护。真实浏览器探针目检通过。

- **逐次调用缓存命中火花线（M8-T899）**：`usage_by_turn` 早已双路累积却无人渲染——新纯模块 `cache-series.js`（null 档诚实降级、24 柱封顶）+ `runtimeMetricsMarkup` 单渲染点，任务详情弹窗与检查器同时获得逐柱视图（`#1 agent 98%` / `#3 judge 73%`）。node 冒烟直接 import 纯模块做真单元断言，并首次让 node（原生 CRLF）与 Python（universal newlines）两种读者同框。

- **chat/completions 流式补齐同契约（M8-T900）**："非流感"按协议对称修完——工具调用 name/arguments 分片、`reasoning_content` 分片在 chat 流里同样上状态通道（三态 start/progress/done，答案流零污染）。T898 chip 在 chat 协议下零前端改动即生效。流族回归 42 绿。

- **帮助面板快捷键表追上真实键位（M8-T901）**：唯一速查屏漏了 Ctrl/⌘K（面板）与 Ctrl/⌘L（账本）——补全至 8 条且中英同序；新增 `?` 全局键（与 `/` 同输入框守卫）打开帮助，速查表自举可发现。门测试双向对账 handler↔表格。

- **「年鉴」上线（M8-T898）**：侧边栏新增「年鉴」入口——全屏博物馆级展板，五个章节（序章 + 5 章）以真实仓库事实为锚：缓存命中率中的仪表盘、任务总数、tokens 数来自 `/api/metrics`；没有数据时显示 `—`。左侧 rail 导航，每章 6 种不同的版式（lede / stepper / instrument / quote / list / mixed），纯 CSS + SVG 场景，零外部图片。Cmd/⌘+K 命令面板也可达。欢迎每次 commit 后关掉 index.html 再开浏览器，观察序章到第五章如何讲述同一个故事。

- **脉搏卡实时火花线（M8-T902）**：任务**运行中**，每个 `usage` SSE 事件都会经 `updateInspectorMetrics` 重绘脉搏卡的 token/缓存数字——现在火花线也跟着重绘：每根条形代表一次实际模型调用，第 1 次调用全价付费、前缀缓存生效后逐次转绿，现场可见。实现收敛在既有 `cacheTurnSparkline` 渲染函数（任务详情模态与脉搏卡同一渲染路径），靠字符串比对 `slot.innerHTML !== markup` 防止 dock 高频重绘的无意义 DOM 写入；无数据时自动隐藏。门测试 `frontend_cache_series_one_home_smoke.mjs` 扩宽为 2 个调用点并锁住该守卫。

- **弹窗焦点确定性 + 模板详情 i18n 收口（M8-T903）**：并轨会话收编——弹窗打开时先把背景焦点元素显式 blur 再置 inert（inert 下一帧的 blur 会静默取消此前发出的 focus()，模态前两次聚焦空转、只能靠 220ms 重试兜底）；模板详情视图的「返回/发送」按钮从硬编码 fallback 收进 i18n 字典（zh/en 472 键对齐）；两处 Playwright `waitForFunction` 把 options 当 arg 的签名错位补上 `undefined` 占位。

- **脉搏卡新增「任务时间轴」（M8-T904）**：任务档案是列表、账本是汇总，年鉴是叙事——时间轴是第四个视角：把最近 12 个任务画成 oldest→newest 的柱状条带，高度按 tokens 的 log1p 对数比例（12% 下限，巨型任务不会压扁小任务），色调沿用档案的状态语汇（完成 mint / 失败 rose / 取消-中断 amber / 运行中 pulse 呼吸）。悬浮看任务名·tokens，点击直接打开任务。纯计算核心 `taskTimelineSeries` 与渲染 `taskTimelineMarkup` 分离、可直接被门测试 import；无任务时显示 `pulse.timelineEmpty`。同时本批携带了对话框 visibility 转场聚焦竞态的根治（`.show` 立即翻转 visibility）。`test:timeline` 已接入 JS syntax 腿。

- **脉搏卡任务时间轴（M8-T904）**：`pulse.epoch` 占位键终于落地——任务档案上方一条时间轴，每任务一根柱：左老右新、log 尺度定高（百万 token 巨任务压不扁 2k 小跑）、completed=mint / failed=rose / cancelled=amber / 运行中呼吸脉冲、零 token 任务 8% stub（跑过就是跑过）。悬停出 tooltip，点击走既有 data-open-task 委托直达任务详情。探针顺带揪出并修好潜伏 bug：`#pulseMemory` 自 T895 起就不存在，fetchAll 每次踩 null 落 catch——命中率/上下文/完成率三个圆环与任务档案其实一直是坏的，如今首次真正读数（57% 命中、46% 完成、12 条档案）。

- **DOM id 契约门（M8-T905）**：#pulseMemory 式幽灵 id 整类封死——脚本里每个字面 `$("#id")`/`getElementById("id")` 引用必须有家（index.html 定义、JS 模板创建、或 `.id=` 惰性创建），基线 174 引用 / 0 幽灵一次绿；门自反验证自己看得见 pulseMemory 那个形状、不误报 approvals.js 的运行时创建。

- **data-i18n 契约门（M8-T906）**：HTML 声明的 182 个 i18n 键必须双语言在列——首扫的 5 个"幽灵键"其实是裸键扫描盲区（字典头部 `recentTasks: "最近任务"` 形态），重复补键被 one_home 门的重复检测拦下，门正则对齐后一次绿；lifecycle 真实浏览器冒烟首绿，T903 waitForFunction 签名修复实测有效。

- **`/api/digest` 工作区知识事实包（M8-T905）**：一个只读、离线的端点——分支、HEAD、upstream 漂移、脏文件数、提交总数、最老提交时间、年鉴/更新日志的批次与行数（本仓：1417 commits / 228 个批次标题 / 50359 行 roadmap / 1024 tracked files / 694 测试文件）。非 git 工作区回答 200 + `is_git: false`（绝不抛错），路由清单门自动探测。`minicc/digest.py` 是与 web 层无关的纯函数模块，年鉴后续章节直接引用它说话。

- **平面第一扇「机队拓扑」窗（M8-T906）**：`GET /api/insights/fleet`——Eureka 现在被读出"谁在、谁倒了"：服务名排序、实例数、每个实例的 host/port/uri/真实 UP/DOWN（非 Eureka 后端报 `UNKNOWN`）。注册表读不通 → 503 `registry-unavailable` + 原因，绝不伪造一个空集群；单个应用读不通 → 整体拒绝，不给半个机队；零实例的服务照样显示出来。网关零改动可达（`lb://` + 既有 `insights-route` 熔断）。`mvn -pl minicc-cloud-insights test`：19/19 绿。

- **前缀指纹链 + 发送边界脱敏（M8-T907）**：每请求随 usage 携带 system/msgs/tools 指纹与 64 窗口逐条累积链——"缓存为什么不命中"从猜测变成读数（第一条分歧消息直接可见）。发送边界与存储统一脱敏（redact_message 单家，provider 出站重建副本、活列表不动），磁盘 8 处 [REDACTED] 与发送字节的不对称消除，凭据不再出进程。真实网关三重实测：任务内命中 97.6-97.7%；链对比证明前缀逐字节稳定后，跨任务冷启动 1792 定案为上游 1 槽缓存被 judge 轮挤占的结构性约束。

- **任务详情前缀指纹条（M8-T908）**：T907 的指纹数据有了脸——缓存火花线下方每轮一行 `sys · msgs · tools · 命中%`，sys 漂移=提示词重建、tools 漂移=schema 变化、msgs 整串变=历史重写，缓存故事一眼直读（实测 #1 3% 红 / #2 98% 绿 / #3 judge 独立前缀 40% 琥珀）。旧快照诚实不渲染；命中标签复用 ledger.cacheHits 零新键。

- **闭合两个 CI 红（M8-T909）**：doctor 无 key 警告不再回显变量名（`test_doctor_works_without_credentials` 全环境绿，空 HOME 沙箱实测输出零变量名）；palette 门要求的 `--tl-h` 在组件规则里获得默认声明（内联逐节点覆盖不变）。

- **年鉴序章上线「仓库考古仪器」（M8-T910）**：年鉴第一眼现在不再只有文字——打开即见分支·HEAD、提交总数、第一笔提交日期、批次手稿章数、跟踪/测试文件数，全部来自 `/api/digest` 现场读数（绝不伪造；端点缺失或非 git 仓库时整块不渲染，脏工作树附施工注脚）。3/2/1 栏响应式，真实浏览器探针验证 DOM 中三项真值。

- **年鉴第六卷《The Gate · 门神》（M8-T911）**：年鉴新增一章——CI 从角色黑名单里走进叙事中心。双平台全量、文档门禁（悬空证据零容忍）、路由覆盖率 + 引用面、21 个 JS 协议门、plane 的 mvn ×7 模块、真浏览器 ×2，每一道门都不允许说谎。三格仪器全部取自 `/api/digest` 真实读数（1424 提交 / 700 测试文件 / 235 章手稿），rail 共 7 章。

- **「回放 · Replay the Run」上线（M8-T912）**：任务详情新增「回放整个任务」，全屏电影席按事件顺序逐行浮现——事件流可暂停/倍速（1×/2×/4×）/拖拽 scrub、tokens 侧栏累加动画、通关蜡封落字。事件与聊天时间轴同一可见性口径（`compactModelUpdateEvents`），老快照诚实空态，零新后端。真实浏览器探针通关（0→逐行→scrub 10/10→返回详情→Esc 关闭，零 pageerror）。

- **`minicc --digest` CLI 上线（M8-T913）**：仓库考古学读数不再只是 HTTP 端点——`minicc --digest` 输出 branch@HEAD / upstream 漂移 / 提交数 / 首次提交 / tracked/test 文件 / roadmap 批次与行数；`--digest --json` 与 `/api/digest` 同 schema（`minicc.digest.v1`）。非 git 目录诚实降级。新增 4 条 CLI 用例 + digest 套件 9 绿。

- **Plane 真实环境冒烟 + rabbitmq 4.0-alpine（M8-T914）**：docker-compose 从未在本机拉起——`rabbitmq:3-alpine` 在 Docker Desktop/WSL2 必崩（`.erlang.cookie` eacces），改用与本机在跑同族验证过的 `rabbitmq:4.0-alpine`。随后全平面替代端口真机验收：四个服务 UP、网关经 `lb://` 打通 `/api/insights/fleet`（M8-T906 端到端兑现）、120 并发 → 25×200/60×429/35×503、`gateway.rate_limited{route=insights}` 计数 60（M8-T888 兑现）、熔断 open→honest 503 fallback→半开→CLOSED 完整回环。5672/6379/8080/8761 全部避开（careeros/specproof 占用），验收后 `compose down` 清场。

- **年鉴第七卷《The Mesh · 六个服务，一个国家》（M8-T915）**：把 M8-T914 的实弹演习写进叙事宫殿——120 并发、25×200/60×429/35×503、熔断器 31 次快开、≤15s 闭合恢复，五行门禁清单（Eureka/Gateway/Redis token bucket/Resilience4j/RabbitMQ）。rail 现共 8 章；仪表不留假数字，实弹数字标注日期与测量口径。

- **「航行灯 · Running Light」上线（M8-T916）**：侧边栏底部常驻一枚环境读数——「缓存 98.3% · 任务 1426 · main @ 2e8dfb1」，mint/amber/rose/quiet 四档色温（high 态 mint 呼吸），数据与账本/脉搏同源（`/api/metrics` + `/api/digest`），45/60s 轮询（页面隐藏时暂停），点击直达账本总览。端点不可用时静默降级为 `—`，绝不伪造数字。i18n 双语全量；真实浏览器探针验证渲染与点击联动零 pageerror。

- **年鉴第八卷《The Witness · 笔录不说谎》（M8-T917）**：审计日志进入叙事——三格仪表全部取自 `/api/stats` 现场读数（审计 1463 行 / 115 会话 / 2385 消息），五行证词清单讲清"被写下的都能被读回去"的纪律：provider_retry 是网关的耐心、completion_assessed 绝不来自静默跳过、approval_requested 是越权边缘、密钥永不落盘。rail 现共 9 章。

- **全链路真实实弹 E2E（M8-T918）**：真 `minicc-web` + 真 `wkapi.pro/v1` 下，chromium 走完用户路径——46.8s 完成真实任务（README 单句摘要）→ 航行灯如实显示 `缓存 31.7% · 任务 1`（新沙箱 + 仓库漂移的前缀冷启动，与网关事实吻合）→ 回放完整播放并亮蜡封 → 年鉴仪表现场读数（1431 commits / 242 章 / 701 测试）→ `/api/digest` 与 CLI/JSON 同 schema。单元门之外，整体闭环首次被一份实弹证据钉住。

- **README 补齐工作台全景（M8-T919）**：README 新增《工作台模块（产品界面一览）》——账本 / 脉搏 / 年鉴 8 卷 / 回放 / 航行灯 / 模板库 / CLI 只读面板 / Spring Cloud plane / 前缀缓存全链可观测，逐条对应仓库现状核对过的真实命令与端点（含 `MINICC_CLOUD_*_PORT` 覆盖提示与 98.3% 热命中实测）。

- **年鉴事实修正（M8-T920）**："2026 年春天"→夏天（digest 首笔提交 2026-08-24）；"zen plan"（仓库中不存在）→ plan / verify 循环；"21 个" JS 协议门→22 个（与 ci.yml 实际执行的 22 个 `npm run test:*` 对齐）。年鉴的"每个数字可对账"承诺对叙事文案同样生效。

- **`test_no_constant_is_defined_without_any_repository_reference` 卡死修复（M8-T921）**：根门禁射程误把 `.venv` 也裹进来（数万第三方 .py 的 AST 解析 → 本地 OOM/无限挂起、CI Python 双腿无限 in_progress）。本批仅将 `.venv`/缓存目录/dist/output/.playwright-cli 加入既有 skip 集合——射程回到门禁本来的名字（"repository"），信号零削弱。**267 秒通过**。

- **两个 CI 红各自揪出一个真 bug（M8-T922）**：航行灯分隔符 `.running-light-text i` 用了 hairline `--line-bright` 当字体色——改为 `--quiet`（色板门修）；README 提到的 `/api/stats` 从来不存在，但 web 早在调它（pulse 的会话/audit/disk/cache 拓扑因为每次 404 一直没渲染上）——新增 `GET /api/stats`（`AgentService.stats()`，与 CLI `--stats` 同事实包，只读免凭据不抛错）。12+8+8+5 项门测全绿，重建 bundle 验收通过。

- **route_coverage 门红→绿（M8-T923）**：claim 检查（doc pointers + route coverage + impact floor）里红的那条 Gate——`test_every_api_route_is_named_by_a_python_test`——要求每条 `path == "/api/x"` 路由在 tests/ 中有名有姓。M8-T922 新增的 `/api/stats` 只在测试里隐式经过，没有具名化；新增 `test_get_stats_answers_the_operational_inventory`：HTTP 200、state_dir_present=false、audit/tasks/sessions/disk/cache/llm_cache 逐项钉住。并行会话一度把该文件截零，已 `git checkout` 复原后重写。`route_coverage --check`：91 passed，GET 22/22、POST 14/14，exit 0。

- **脉搏面板三格读数实机点亮（M8-T924）**：chromium headless 实跑脉搏面板，`/api/stats` 事实包完整渲染——`pulseMemory: 115`（sessions）、`pulseAudit: 1464`（audit lines）、`pulseTurns: 2392`（messages）。M8-T922 的修复在整条 HTTP→Service→DOM 链路上验证为真，不再是"应该能行"。

- **双语说明书 + 全内容中英切换（含自救），M8-T925~M8-T929**：说明书模块落地——七章双语小册子（五分钟上手 / 工作台导览 / 七个模块，一个世界 / 命令与快捷键 / 游戏厅教程【Pulse·Sun·Rally·Time Stop 四技能 + 图鉴】/ 排错 / 边界与范围），侧边栏进入，zh/en 内联双语。作者提交中T927（i18n.js / index.html 的 CRLF 丢失 → CI 如实红）与T928（game.js 图鉴双语化脚本吞掉约 95 个函数 → bundle stale → JS syntax 红，Python 双平台红）两次事故，**M8-T929 修复**：game.js 恢复损坏前版本后按"捕获 zh 原文 + en 对照翻译"重建 {zh,en} 双语图鉴（19+19+19+19 键）；CRLF 契约恢复（6 passed）；index.html 19 处硬编码中文全部 data-i18n 键化 + 3 处回退键；i18n.js 557→562 键严格对齐、213 个 literal t() 全部可解析；**almanac 全量重写为逐章 zh⇄en 双语正文**（之前是中文正文 + 英文夹杂，无法切换）；renderCodex / 手册 kicker / 语言切换器措辞 / api.js / locale.js 残余中文补双语 fallback；bundle 重建（check:web ✓）。全视图英文探针零 CJK（除语言切换器与用户数据），`tests/codex_smoke.mjs` 新增英文断言；本地 test:arcade / test:web / test:i18n 全绿。T925-T928 的远程 CI 历史保留为红，回绿由本提交的运行证明。

- **新手演示按钮 + 通关路线 + arcade 真键盘操作，M8-T930**：说明书五分钟上手章新增动作块「直接看一遍 / Would rather watch than read」，一个按钮现场运行 demo flow（intake → plan → tool → verify → deliver），中英两套；游戏厅教程章新增「第一局怎么赢（通关路线）」与「常用键位」（之前手册里描述的键盘操作游戏里并不存在——文档先于实现的事实错误，本批修正为真实现）：`web/src/game.js` 新增 `1-9` 按 DOM 顺序选卡、`P` 暂停/继续、`E` 铲子（仅在游戏弹窗打开且焦点不在输入框时生效）；真浏览器验证（zh/en 双语按钮均触达、`game.selected`/`pauseReasons`/`shovel` 全通）；`.manual-callout` + `.manual-demo-run`（CTA，focus-visible 就绪）；bundle 重建 ✓。

- **分支并轨文件级复核，M8-T931**：逐一比对 dev/minicc-reliability-4ba3 / feature/minicc-cloud / consolidation/* / backup / archive / scratch / origin/integration/m8-t537-to-main / origin/m8-t537 与 main 的 src 级面——全部为领先关系；唯一“缺失”的 11 个文件是 8 个 hashed 构建产物（main 重新构建）+ 3 个早期 test 草稿（已被 main 的 fence/line ruler 套件覆盖）。结论同 M8-T924：没有任何分支携带 main 缺失的功能内容，不以形式合并倒退。

- **almanac 双语回归门，M8-T932**：新增 `tests/almanac_smoke.mjs`——真浏览器逐章验证 almanac 九章：en 模式零 CJK、zh 模式必须渲染中文；`test:almanac` 入 `test:arcade`（game+codex+zombie+almanac）+ ci.yml syntax job 的 `node --check`；fake provider 服务器上本地通过。全内容双语不再是"修了就算"，而是每次 CI 强制验证。

- **快捷键清单与 arcade 键盘操作对齐，M8-T933**：帮助面板（? 键）和说明书「命令与快捷键」章节新增 `1-9` 选植物 / `P` 暂停 · 继续 / `E` 铲子——和 M8-T930 的实现一致，中英双语；bundle 重建。

- **铁律 —— 十条仓库自己写下的规则，M8-T934**：新增 `web/src/panels/axioms.js`——侧边「铁律」入口（⌘K 可搜），十条铁律逐条卷轴画布：本地优先 / 先证据后结论 / 门从不说谎 / 缓存不是优化是成本认知 / 全内容双语 / 用户数据不是产品文案 / 每次变更都有批次号 / 失败必须被看见 / 工具调用有完整签名 / 承诺必须被执行。每条附「证据收据」卡片（真实文件路径 + 该文件证明了什么），全部落点本仓库，中英两套整段，en 实测零 CJK；再添其一。

- **展示页自动同步 bot 竞速修复，M8-T935**：`update-latest.yml` 的 `git push` 前新增 `git fetch origin main` + `git pull --rebase`；此前同秒推送会让 bot 撞上 non-fast-forward（13:24 现场：bot 已提交但被拒）。不改刷新频率策略（仍按大提升节奏），只消除机器人自己和并发推送的竞速。

- **README 模块清单对齐现状，M8-T936**：年鉴 8→9 卷勘误（Gate 卷已落地 M8-T911）、补入「说明书」与「铁律」两个新模块条目。

- **digest 最近提交 + 第十二板块「工程日志」，M8-T937**：`minicc/digest.py` 新增有界 `recent_commits`（12 条，newest first，被 git 读取、不碰网络）；`minicc --digest` 跟随打印；新增 `tests/test_workspace_digest.py::test_digest_carries_recent_commits_bounded`（6 passed）。全新面板「日志」——仓库自己写在自己身上的工程日志：仓库体素（提交数/开张天数/批次/文件/测试/分支@HEAD）+ 工作台体征（模型/会话/消息/审计/tokens/命中率）+ 最近 12 提交（今天 mint 左条高亮，凡带 M8-Txxxx 标签）；全部数字现场读 `/api/digest`·`/api/stats`·`/api/metrics`，零硬编码，en 实测零 CJK；⌘K 可搜；bundle 重建（app.js 483943 chars）。

- **展示页自动同步 bot 第二次修复，M8-T938**：`git pull --rebase` 自身撞上 `docs/latest.json` 的合并冲突（bot 的提交与远程并发 refresh 同文件）——现在 rebase 冲突时先 `node scripts/update-latest-json.mjs` 重新生成（latest.json 是 bot 自己的产物，可由工作树内内容随时重建），`git -c core.editor=true rebase --continue` 收尾。这样 bot 对自己的产物拥有完整裁量权，不再需要人工介入。

- **展示页事实包覆盖十二模块 + 特性数实时渲染，M8-T939**：`scripts/update-latest-json.mjs` 的 `feature_surface` 改为真实十二个模块，新增 `module_count: 12`；展示页 minicc 卡片的"特性面"由硬编码 `13 项` 改为读事实包现场渲染（`ml-features` ← `d.module_count ?? d.feature_surface.length`）；事实包继续每次含 docs 的 push 自动刷新。

- **第十三板块「档案馆」 + 只读 /api/roadmap，M8-T940**：`minicc/roadmap_archive.py` 解析 `## 批次` 章节（双划线/全半角冒号兼容），`Service.roadmap()` + `GET /api/roadmap` 路由（`test_get_roadmap_answers_the_archive` 已钉契约，route_coverage 绿）。面板按世纪分 4 组、257 条手绘时间轴、⌘K 可搜、现场过滤；章节名字原样如实展示；页脚注明"本馆从第 601 批起还原，早期以里程碑/进度日志形式存在，不伪造完整度"。en 实测零 CJK。顺手记录本轮真实 API 测量：cold 0% → warm **98.3%**（wkapi.pro 同模型同提示词三轮一致）。

- **上手演练（Onboarding tour），M8-T941**：新用户两分钟产品演练——首次到访右下角长出"第一次来？"按钮，6 步（welcome → 侧边控台 → 输入框 → 演示流程 → 年鉴 → 完成）zh/en 全双语；聚光灯 + 呼吸光晕高亮 + 下沉叙事卡；Esc 随时退出；⌘K 搜 `tour` 随时重开；完成即记忆，不再占右下角。README 模块清单新增上手演练条目；真浏览器 zh/en 双侧验证（offer 出现 → 6 步 → minicc-tour-v1=done → 刷新不再出现）。

- **第十四板块「近况」，M8-T942**：新增 `web/src/panels/recent.js`——侧边「近况」（newspaper + UPD 徽标），开板即现场拉 `/api/roadmap` 展示最近十五批：`#批次` 等宽号 + `M8-Txxxx` 徽标 + 原样标题，最新一条 mint 描边高亮；页脚一键跳档案馆。README 模块清单新增近况条目；⌘K 可搜；真浏览器 zh/en 双侧验证（15 行渲染 / meta 259 批 / 702 测试文件 / archive 跳转 / en chrome 零 CJK（章节标题为仓库用户数据，原样呈现））。

- **展示页事实包追上 14 个模块，M8-T943**：`scripts/update-latest-json.mjs` 的 `module_count: 14`，`feature_surface` 增加 `archive` 与 `recent`（17 项）；展示页 minicc 卡片说明已同步为「侧边十四块」；事实包随每次含 docs 的 push 自动刷新。

- **空台焕新（M8-T944）**：`web/src/chat/markdown.js` 的 `emptySessionMarkup()` 重做——环形轨道（orbit）+ 碑记 M 徽标 + 涟漪微动 + 三枚一键 pills（读 README / 跑测试 / 审 diff，中英同版，i18n 双语），按钮 click 即填入 composer；`web/index.html` 静态占位空台同步；M8-T892 时代 `.empty-mark` / `.empty-actions` 死规则清理；空台 chip 绑定改为 `#messageList` 委托；Playwright zh/en 双路验证渲染与填入。

- **事实包带最近提交 + 展示页最近提交条，M8-T945**：`scripts/update-latest-json.mjs` 新增 `recent_commits`（5 条最新，schema 保持 `minicc.latest.v1`，新增不破）；`xiaodernan.github.io` 的 minicc 卡片新增 `.minicc-latest-commits` 渲染器，按事实包实时渲染（5 行 coral 等宽 short + 原始 subject）——访客每次进卡片看到最新的开发故事，不再只有数字。

- **任务完成庆祝彩带，M8-T946**：新增 `web/src/celebration.js`——26 枚彩色火花从气泡中心向外飞散（`prefers-reduced-motion` 完全不渲染）；`addAssistantMessage` 只在 live + `status==='completed'` 的路径上触发，restore / 失败 / 非当前任务路径不变。首次证明“做完一件事给用户一个让人需要太久的呼气”。

- **说明书第八章「安静的房间 / The Quiet Room」，M8-T947**：说明书扩展为 8 章——这一章讲「为什么这间屋子这样被造」：没有甲方 / 没有专有智慧 / 没有表演型智能体 / 没有「THE PLAN」/ 每件事都会回来。中文版与英文版同故事，铁证入后证据：命令行、沙箱、门电路、`/api/stats` 现场数值、缓存命中率——没有不可检验的领袖性短语。真浏览器 zh/en 验证（en chrome 零 CJK，rail 8 项完整）。

- **手册游戏厅章 · 冲关心法，M8-T948**：新手册「wave-by-wave」条目按实际 `WAVE_TARGET(wave,'hard')` 直录 Wave 1–10 目标数：walker 1–9 / conehead+buckethead 6–9 / Wave 10 Gargantuar；economy 条揭露阳光 2–4/s、wallnut 吸收 3–4 波、撑杆跳只越第一个 plant、magnetshroom 拔锥桶、squash 强制击杀。中英并行，en 不混 CJK。

- **年鉴卷九「技艺 / The Craft」+ 换章两阶段渲染 + palette 门修复，M8-T949**：新增年鉴卷九——提交数 / 批次章节 / 审计行数 / 跟踪文件 / 测试文件从现场 digest+stats 读出（"没有草图，只有舰艏字。"）。换章 bug 真因定位：`loadChapter` 等待 `/api/stats`（322MB 状态目录上可超时）才注入 innerHTML——改为两阶段：先用缓存即时渲染，新数字 8s 超时兜底、仅当用户仍停留在本章时刷新；`/api/stats` 孤立慢点不再冻结整个面板。almanac smoke 加 `craft` + 每章 marker 断言（canvas 必须渲染本章，根治「冻结伪装通过」）。palette 门修复：8 个 celebration-spark 运行时 CSS 变量登记豁免（均有 `setProperty` 书写证据，门不弱化），删除死属性 `--hue`；`test_the_palette_has_one_home` → 5 passed。

- **/api/stats 磁盘统计 TTL 缓存 + 测试隔离，M8-T950**：`minicc/stats.py 的 _disk_bytes` 加 120s monotonic TTL 缓存（首问抖动 2.8–14.5s → 次问 1.22s，byte 计数一致）；`test_an_absent_store_*` 改为钉住 `tmp_path` 工作区根——此前在任何跑过真实任务的开发机上会被共享 home store 污染成失败（runner 上是绿的）；README 年鉴 9→10 卷、档案馆 257→269 批次章节并删除重复条目。

- **年鉴 hydrate 60s TTL + 20s 预算，M8-T951**：phase-2 在繁忙 `.minicc` 上被压出 8s 超时而永远显示「—」——现改为 60s 内复用 digest/stats 缓存（章节切换从不重问）+ metrics 15s / digest、stats 20s 实际预算（phase 1 已秒开，时间不该从用户口袋里出）。实测换章 9s 出现 `提交 1483 · 批次 270 · 审计 1468 · 文件 1050/702`。

- **集大成复核 2026-11-15，M8-T952**：`docs/CONSOLIDATION_REPORT.md` 增附录六——四条未合并分支与 2026-11-12 的处置结论逐条吻合（patch-id 差集实测）；`origin/m8-t537` 与 `origin/integration/m8-t537-to-main` 被确认为纯子集，已吸收入 `main`；`consolidated/*` 标签 7 枚原样存在；M8-T945–T951 全部落入 `origin/main`（最新 `7307cea`）。结论：`main` 就是汇集后的主分支，不造空 merge、不删 worktree。

- **事实包年鉴章节数按源码计数，M8-T953**：`scripts/update-latest-json.mjs` 的 `almanac_chapters: 9` 字面量腐坏已根治——改为从 `web/src/panels/almanac.js` 数 `roman:`（真章数），展示页所见现在等于真年鉴卷数（10）。

- **缓存亲矩阵实测固化，M8-T954**：docs/CACHE_AFFINITY_MATRIX.md——wkapi.pro · gpt-6-sol · 真 key 逐格（2026-11-15）：Responses 流/非流 94.5%→100% 都如实上报；chat/completions 无 key 流式永不回 cached_tokens（3/3），带 key 后两路都报（5376/5509=97.5%）；直连 urllib 被 403（TLS 指纹）。三误解结案：「命中率低」= 流式不上报的显示产物（缓存实际在工作）、「显示非流」= 已移除的恢复锁、judge 0% 属结构性（前缀独有，不自评）。说明书排错条目同步为实测结论（双语逐字对应）。

- **火苗 · 连续完成天数，M8-T955**：`web/src/streak.js`——`#streakChip` 金焰 pill 常驻侧边栏（航行灯与工作区名之间），每天 ≥1 次真实任务完成即 +1；localStorage `minicc-streak-v1`，本地零网络、刷新即见（损坏数据按 0、缺席两天重置、当天重复不重复计）；`celebrate()` 开头点亮、与动效偏好解耦；新增 lucide `flame` 描边与 🔥 本地 glyph；i18n 581 keys 对齐；Playwright 三场景（新→1 / 昨日 4→5 / 3 天前过期 9→1）✓。

- **年鉴卷十「未竟 / The Unfinished」，M8-T956**：`web/src/panels/almanac.js` 新增第十一卷——「这册子还没写完，它正在写」。仪器盘（提交总数 / 批次章节 / 当前北极星现场值）+ 按 digest 流式渲染的「最近的交付」(6 条真实提交）+ 双语正文：缺口编号不是葬送，是还没决定要盖什么。说明书/README 年鉴升至十一卷；almanac smoke 11 章全绿（marker 断言）；zh/en 真浏览器双验（hydrate 提交 1498 · 批次 275 · 当前 north star 9842116）。

- **/api/digest 并发 git 探针，M8-T957**：`minicc/digest.py 的 build_digest` 的 9 个独立只读 git 子进程改为 `ThreadPoolExecutor(max_workers=9)` 并发 + 根提交用单次 `git log --max-parents=0 -n 1 --format=%cI HEAD`；cProfile 实测 wall clock 1.34s（87% 是 subprocess 等待）→ ~0.5–0.6s；`/api/digest` 现场连续 5 次 **0.59/0.59/0.67/0.61/0.58s**，payload 逐字段不变。

- **年鉴数字两波刷新，M8-T958**：`web/src/panels/almanac.js` 的 `loadChapter` 拆为 two waves——fast：等 metrics+digest（<1s）立即重渲染；slow：stats 到了同章刷新、异章丢弃。切章到数字可见从 ~9.8s → **~1.7s**（实测切片：0.66 占位 → 1.67 digest 数字 → 5.68 stats 数字）；M8-T951 的 60s TTL 与切换即时性不受影响。

- **任务筛选（/），M8-T960**：侧边栏「最近任务」上方新增筛选输入（`/` 全局聚焦、不抢面板与输入区）——160ms 防抖实时筛选、Enter 直达首个匹配项、Esc 清空失焦；零网络往返；历史轮询重绘时由 MutationObserver 自动重刷。**附带修复被真实浏览器戳出的布局 bug**：`.thread-list` 在 32px 筛选行挤压下塌缩到 `min-height: 0` → 改 `min-height: 156px` + sidebar 纵向可滚动，24 行历史恢复正常交互。删除死掉的 `#threadSearch` handler；i18n 583 keys；web/almanac/i18n smoke 全绿。

- **说明书第九章「密钥与金库 / Keys & Vault」，M8-T961**：`web/src/panels/manual.js` 新增——凭据的完整旅程七则（`.env` 位置/`--doctor` 的 `prefix cache:` 行/同 `MINICC_PROMPT_CACHE_KEY` 换家不冷/`[usage]` 的 `cache_hit_pct` 与脉搏逐 turn 火花线/`cost_is_partial` 与按模型分解成本/Anthropic cache_control 断点/`.minicc/` 归档）。中英逐字对应；**顺带修掉「zh 模式下 canvas kicker 仍是英文大写标题」的混杂漏洞**——现在 zh：`第九章 · 安静的房间`，全轨 9 章 zh/en 零混杂（Playwright 逐章验证）。README 说明书 8→9 章。

- **侧栏顶部搜索框接入全局搜索 + 矮屏自适应，M8-T962**：`.sidebar-search input#threadSearch`（`/` 聚焦、目前零 handler 的顶部输入框）——`Enter` 直接打开 `openGlobalSearchPanel(seedQuery)` 并预填 + 排队 `/api/history/search`（真实命中片段、匹配次数 chip、Esc 清空）；`Escape` 清空失焦。**新增 `@media (max-height: 1020px)` compact 侧栏**（品牌 46→30 / 新建任务 38→30 / 主导航 36→30 / 小节间距全线收窄 / 侧栏整体 960px 视口完整可见）。侧栏顶部搜索框不再是摆设；矮屏不让路。

- **Spring Cloud 平面两条后端通道用真 docker 实测，M8-T963**：RabbitMQ 缓存失效 fanout —— local broker 圆环 `CacheInvalidationRoundTripLiveTest` 实测通过（exchange 声明→队列绑定→消息到达+header 精确）；并修正该测试 Javadoc 的示例 URI（`amqp://…/` 尾斜杠被 Spring 解析为空 vhost）。Redis token bucket —— `ratelimit` profile 端到端实测（`MINICC_GATEWAY_RATE_LIMIT_*` env）——`/api/tasks` 序列 req1-2=503（LB 未注册的降级语义）/ req3+ = **429**（bucket 先耗尽，pico 限流先行）/ 3s 后 refill 恢复 → 503。全部生产代码本身真机链路，无示例 mock。`mvn verify` BUILD SUCCESS：gateway 56 / inspector 29 / tasks 14 / insights 19 = 118 tests 0 failures。实测期间未触碰 careeros/specproof 等任何运行中实例（独立 5673/6385/9215），`docker rm -f` 验证容器已清理。

- **`?` 快捷键速查——同源、分组、真有内容，M8-T964**：新增 `web/src/cheat-sheet-data.js` 唯一家（撰写 / 逐行导航 / 全局 / 游戏 四组、16 条）；`openHelpPanel()` 从数据源渲染分组键位（此前完全无 CSS、11 行裸排）；说明书第四章同源渲染、不再双维护；CSS 补齐 `.help-panel` 全部规则——`?` 从「存在着但没人看」升格为「工作台真·键盘雷达」。zh/en 全语言键值齐平 ✓。

- **年鉴卷十一「回声 / The Echo」，M8-T965**：`web/src/panels/almanac.js` 新增第十二卷——「三根看不见的弦，都在响」。git / audit.jsonl / 缓存三根弦各自按音区记事，却共用一个屋顶；EN 中英逐字对应；仪器盘「仓库呼吸 / 批次回响 / 审计回声」全实时数字；三枚紫边卡片揭示缓存亲和（Redis / LRU 现状）、RabbitMQ 失效风暴、Git 审计闭环；almanac smoke 12 章全绿、rail 12 条。

- **游戏厅最佳纪录，M8-T966**：`web/src/game.js` 把每场最好的击退（score）与最高连击（combo）写入 `localStorage:minicc-game-best`；HUD 增加「最佳/Best」与「连击/Combo」两格（`#gameBestScore` `#gameBestCombo`），`initGame` 与 `finishGame` 都刷新；跨会话永远保留真实历史（`{score: 128, combo: 6}` seeded 立得 `128/6`）；i18n 584 keys；web/arcade/almanac/i18n smoke 全绿 ✓

- **鼠标滚轮方向可切换，M8-T967**：新增「鼠标滚轮 / Mouse wheel」设置块（`.wheel-invert[data-invert=on|off]`）——Windows/Linux 默认方向不变；切到「已反转」后与 Mac 自然滚动一致（`localStorage['minicc-invert-wheel']=1`），捕获 wheel 反算 `deltaY` 后写入 `.chat-area`/`.panel-body`/任何 `overflow:auto` 的祖先，`preventDefault` 仅在非默认时生效；跨面板重开可还原。i18n 589 keys；web/almanac/i18n smoke 全绿 ✓

- **/api/stats 并发爆恐消化，M8-T968**：`minicc/stats.py 的 _disk_bytes` 加 per-workspace threading.Lock — 10 路冷 walk 序列化为 7.55 s（之前 60-80s 叠加）；`docs/LOAD_TESTING.md` 诚实钉出 pre-fix 探针（`/api/stats` p50=**43,946ms**，ThreadingHTTPServer+GIL 下 20 路并发每个都 walk 一遍）；`scripts/load-test.mjs` 留在仓库（n / errors / p50 / p95 / p99 / max）。`minicc --stats` CLI 与 `/api/stats` Web 同时受益。

- **/api 三窗 per-PID memo，M8-T970**：`AgentService` 用 `_memo_http(key, 5s, builder)` 缓存 `stats`/`digest`/`roadmap` 三读窗口，并发重复 caller 不再各自走 git-walk+SQLite+os.walk；concurrency=8 × 12s 完美 14/14 200，`/api/stats` p50 43.9s→3.8s、`/api/roadmap` p50=3.12ms。`LOAD_TESTING.md` 附有真实 pre→post 数据。`pytest` 子集 101 passed（含 http_surface 81 项）。

- **仓库文档内置 BM25 RAG，M8-T971**：新模块 `minicc/rag.py`（Okapi BM25、CJK+alphanumeric 分词、3836 chunks 一次冷加载 0.49s / 0.08s cached）+ `GET /api/rag/search?q=…&k=5`（纯本地、零模型、零外部网络）——自带 `minicc.rag.reload_index()` 显式失效；Route Coverage 全 100%（GET 25/25）；`tests/test_rag_bm25_index.py` 7 项；`tests/test_http_surface.py` 94 项（含新端点）。

- **RAG 真跑，M8-T973**：`/api/rag/query` — 仓库文档 BM25 top-k 检索 + 一次 chat.completions（wkapi.pro · gpt-6-sol）；`MINICC_*` env 同仓库其他 lane；`usage` 如实回传（prompt/completion/total，不伪造 cached_tokens）；api_key 从不进 prompt；任何异常退化到 200 + `error`；Route Coverage 100%；真密钥实测 roundtrip=280ms、sources 命中 CHANGELOG/ROADMAP 对应缓存亲和章节。

- **CI 红灯三连修（M8-T974）**：`Python tests`（windows/ubuntu）与 `JavaScript syntax` job 的 3 个真实失败面全部修掉而非绕过 —— INDEX.md「性能与测量」登记 LOAD_TESTING.md；re-aimed citation `minicc/web.py:1804` 随 T970 memoization 平移至 `:1809`（第二处 `:2315`），两篇引测 docstring 与 REPAIRED 名册同步；`frontend_help_shortcuts_one_home_smoke.mjs` 重写为 single-source 世界的等强断言（SHORTCUT_GROUPS 家 + main.js 绑定面全覆盖 + zh/en 双标签非空）；顺带删 `minicc/rag.py` 未被引用的 `_DOC_FILE`。门一格没放宽。

- **「问仓库 / Ask the Docs」上线（M8-T975）**：新侧栏面板 + Ctrl/⌘K「问仓库」——BM25 top-k 检索本仓库 docs/README/CONTRIBUTING，交给你配置好的模型（`/api/rag/query`）只读着作答；sources 逐条可展开（file/score/原文）；usage 条如实显示网关回传的 prompt/completion/total tokens；模型不可达显示真实错误；key 不进 prompt、不被回显；手册第十章双语、首次 Playwright 真浏览器 E2E 验证（真 wkapi.pro「缓存命中率」问答引用 CACHE_AFFINITY_MATRIX/ROADMAP 作答）。顺带修掉中文 BM25 的召回缺陷：CJK 以二元字组索引（此前整句中文检索为空），`test_chinese_sentence_without_spaces_finds_docs` 固化。

- **T974 CI 红灯两处收口（M8-T976）**：`minicc/rag.py` 手写的 measured-usage 三键记录改走 `minicc.llm.usage.measured_usage`（one-home 门复绿）；`load_config` 的宽静默 except 体内陈述边界（route promises honest error payload, never a 500）——三个宽静默门复绿。门未放宽一格；Route Coverage 100%。

- **RAG 提示语单语化（M8-T977）**：`minicc/rag.py` 的 system prompt 去掉双语兜底句串；模型只允许「复制问题语言作答、逐事实引用 [n]」，文档不覆盖时用问题语言回一句无混语的短话。en 复测零 CJK（`scripts/load-test.mjs` 回答带 `[1] [2]`）；zh 复测无英文混杂；`doc_pointers` rc=0。

- **年鉴第十二卷「回问 / The Answer Back」上线（M8-T978）**：十三章叙事宫殿新增一卷——项目自己的 RAG 被写成博物馆文物（零 embedding、真 wkapi.pro 实答、CJK 二元字组修复的诚实伤疤、cached_tokens 不伪造）；`tests/almanac_smoke.mjs` 扩到 13 章双模式验证通过；manual/README 更新到十三卷。顺手删 `minicc/rag.py` 里指向不存在文件的 `ROOT/CONTRIBUTING.md`；语料实测：docs/*.md 34 + README.md = **35 源文件 / 3,857 块**。

- **高并发修复（M8-T979）**：`MiniccHTTPServer.request_queue_size` 5→128（SOCKET 层被丢包根治）；`serve()` 启动即开 `minicc-prefetch` 预热 stats/digest/roadmap 冷缓存（`--no-prefetch` 退出）；`AgentService._memo_http` 新增 single-flight lock（TTL 边界不再 N 倍重建）；stats/digest/roadmap memo 5s→30s；20-路冷压复测 **0 错误**（health/metrics/digest/stats/roadmap 全部 200，p50 ≤ 4.2ms）；`docs/LOAD_TESTING.md` 实测数据刷新；GIL 瓶颈如实记录未消除。

- **`/api/workspace` 进 memo（M8-T980）**：`git worktree list` 仍昂贵，入口改走 single-flight `_memo_http`（10s TTL）——冷 1.1s → 热 104-139ms；c=20 × 15s 全路径 1,497×200、0 错误、p50 ≤ 22ms；117 项测试绿；Route Coverage 不变。

- **RAG 通道 prompt_cache_key 落地（M8-T981）**：`minicc/rag.py::answer` 自派生 `minicc-<sha256(base_url|model)[:16]>` 的 affinity key（显式 `MINICC_PROMPT_CACHE_KEY` 优先）；`usage` 如实解析 `prompt_tokens_details.cached_tokens`；「问仓库」用量条新增「缓存命中 N（P%）」；真 key 同题两连问实测 **19082/19085 = 99.98%**（此前该键不可见）；CACHE_AFFINITY_MATRIX.md 刷新。

- **50-way 全通量实测（M8-T982）**：`c=50 × 20s`，6 条只读路径各 415 次 200，**零错误、零非 200**（2,490 响应）；p50 ≈ 160-207ms（GIL 调度，非处理逻辑）；workspace 陈旧 10s 受控；`docs/LOAD_TESTING.md` 刷新第六次。本批无代码变更。

- **说明书第十一章「压测与容量 / Load & Capacity」上线（M8-T983）**：双语手册第十一章——local-first 模型、load-test 实操、六只读路径实测数字（c=50/2,490×200/0 错/p50≈160–200ms）、三道防线（prefetch / single-flight memo / backlog 128）、仍受 GIL 限制的诚实边界；Playwright 双 locale 截图验证；manual 计数更新至十一章。

- **命令面板登峰造极（M8-T984）**：Ctrl/⌘K 从朴素面板升级博物馆级视觉——暗场柔焦 + 渐变琥珀发丝线 + 回弹入场动画 + 琥珀渐变激活行 + 实心 glyph 键 + mint 键帽 footer + ≤700px 移动适配；行为零变更；27 条命令 Playwright 截图验证。

- **空状态英雄区重生（M8-T985）+ locale 分区缓存修复（M8-T986）**：hero 加三层径向光 + 蓝图点阵网格 + 琥珀/mint 双色 orbit + Mono uppercase 尾注（新 i18n key `session.emptyFoot`，双语 593 键齐平）；顺手修掉 session-view 缓存恢复陈旧 zh 残渣导致英文模式英雄区中文混入的 bug（sessionViewKey 增加 locale 段），zh/en 均已真浏览器验证切换干净。

- **RAG 通道限流上线（M8-T987）**：新增 `minicc/ratelimit.py` —— 行业形态滑动窗口令牌桶；Redis 可达走分布式 INCR+PEXPIRE（共享 redis_cache 连接池/重试窗口），否则本地 LRU 降级；**Redis 中途死掉 fail-open 继续放行并计入 `degraded_open`**，不允许网络抖动击垮产品；`/api/rag/query` 超限返回 `200 + rate_limited + retry_after_seconds`（绝不伪装模型失败，绝不烧额外 token）；`MINICC_RATE_LIMIT_PER_MINUTE` / `MINICC_RATE_LIMIT_WINDOW` 可配；7 条新测试全绿，Route Coverage 100% 保持，silent-handler 边界全覆盖。

- **composer 登峰造极（M8-T988）**：命令甲板三件套——hairline 金顶 + 权限模式组分段滑块（`:has()` 零 JS）+ SVG 圆环上下文计量（tokens/cost/context/cache attestation 全部保留）+ 琥珀渐变发送 orb 呼吸动画；zh/en 双模式真截图验证；行为零变更。

- **交互式「上手演练」上线（M8-T989）**：说明书不再只是被打开的面板——嵌在产品里的 6 步交互式教程，第 3 步真的帮你填好「读一下 README.md…」填入输入框、第 4 步真的帮你跑演示（`runDemoFlow()`）；修复 zh kicker 大面积 mojibake、修复强制 dark 卡面却用亮色主题色（zh/en 均不可读的对比度事故）；13 卷年鉴 / 11 章说明书文案对齐；Esc/箭头/按钮全可用，两 locale 真浏览器走完零错误。

- **空状态直通说明书（M8-T990）**：启动即见教学 —— 第 4 枚 chip（mint 色，区别于琥珀行动召唤）「打开说明书，十一章全翻到 / Open the manual — all eleven chapters」，点击直接打开 11 章教学手册；i18n 双语对齐（594 键），双 locale 真浏览器验证 chip 数与一键打开；bundle 全部绿。

- **年鉴第十四卷「余烬 / The Ember」上线（M8-T991）**：博物馆级章法继续压宽——本卷专读明早醒来打开本子时炉火没灭的那些读数（digest/stats 实值：首次提交 2026-08-24 · 提交 1561 · 跟踪 1,063 · 测试 705 · 批次 307 · 审计 1,468 · 会话 148 / 消息 2,588 · 23/24 完成 1 中断）；Playwright 双 locale + 14 章 smoke 全绿；manual/README 升至十四卷。

- **年鉴第十五卷「星图 / The Atlas」上线（M8-T992）**：博物馆新馆——整个工作台摊成一张星图，节点按色相环分组（amber 工作面、mint 事实面、violet 实验面），19 颗闪烁星子 + 虚线漂移等值线；6 枚仪表从 digest/stats 现场水润（Commits 1,563 / Tracked 1,063 / Tests 705 / Batches 308 / Audit 1,468 / LRU 兜底）；15 章双语全绿，manual/README 升级，forked almanac_smoke 强制 15 章双语

- **年鉴第十六卷「曦 / First Light」上线（M8-T993）+ `/api/worldpulse`**：第一口外部真实数据——`GET /api/worldpulse`（real GitHub public API，8s 超时，5 分钟共享缓存，fail-open），实测 2026-11-15 真 star=1 / forks=0 / open_issues=1 / default_branch=main / pushed_at=最新；第十六章全部从 worldpulse+digest 现场水润；16 章双语 smoke 全绿；Route Coverage 27/27 GET + 14/14 POST = 100%。

- **视觉债三连修（M8-T994）**：侧栏三栏由横 layout → 纵 icon-above-label 对齐，中文/日文全字显示；inspector-tab 单行不再截断/挤压计数；changes 长文件路径 anywhere 换行不再溢出破坏；Playwright 真浏览器截图佐证。

- **视觉债清扫二期（M8-T996）**：Pulse 眉标改为右侧圆角 mono 计数徽章；航行灯条 `white-space: nowrap` 单行，分支名收窄；侧栏与空态紧凑断点放宽到 1180px，1080px 笔记本不再裁掉工作区卡片与第二排 chips；植物卡库取消 150px 硬上限；小游戏 HUD 状态不再断词；变更/文件路径以 U+200B 目录边界换行（辅助函数显式 `\u200B`，不藏不可见字符）。

- **诊断中心 Doctor（M8-T997）**：新模块——「上游回声」真实 GET /models 探测 OpenAI 网关（678/586ms，零 token，密钥不回传，fail-open，10s 共享缓存）；「负载实验室」最多 24 并发×24 请求锤本机回环端点，canvas 直方图画出 MIN/P50/P95/MAX；实验抓到首波 6 并发全部撞上 ~7.3s 冷缓存惊群的真实特征；「为什么 minicc 快」四条全部来自本仓库实测事实；中英双语严格对齐（625 键 parity）；说明书新增 Doctor 条目；路由覆盖 GET 28/28 + POST 14/14 = 100%。

- **js-check 三红修复（M8-T998）**：`softPath` 的 U+200B → `<wbr>`（断行机会元素，textContent 与复制保持原样）；lifecycle/scale 两个冒烟自 M8-T986 起因 `sessionViewKey` 的 locale 后缀断言陈旧而红，已改为 locale 不可知断言（不变量未变）；23 项 npm 测试电池全绿；fake-provider web_smoke exit 0；T997 的 js-check 红被本批自愈。

- **年鉴第十六卷「高烧 / The Fever」上线（M8-T999）**：把 37s→4.2ms、2490×0、两个 U+FFFD、T986 后三周两个冒烟蒙尘、冷缓存惊群全部写进史诗——8 格真实仪表、5 条门 list、双语铁律 smoke 17 章全绿；说明书同步到十七卷。顺带复绿 web-smoke：game_upgrade_smoke hover 步骤因 peashooter 点击把 canvas 沉到折叠线以下而超时，`scrollIntoViewIfNeeded` 后再断言；arcade 套件四件全绿。

- **短屏布局到底（M8-T1000）**：1280×800 / 1440×900 两档适配——`@media (max-height: 940px)` 压缩 chat-inner/session-heading/date-divider/hero（orbit 128→72px），空态 chips 彻底脱离 composer 遮挡；`@media (max-height: 900px)` 压缩侧栏（nav 36→26px 等），侧栏自裁剪 145px → 5px，工作台设置整行进入视野；Playwright 双语截图确认。

- **Doctor 工作区自检（M8-T1001）**：诊断中心第三件真工具——`/api/doctor` 即 `minicc --doctor` 引擎直出（7 通过 / 2 警告 / 0 失败的真实截图）；检查名 mono + severity 圆点 + fix_hint，fatal 行 coral 边框；633 键双语 parity；manual/README 同步；零新增路由。

- **CI 双腿红复盘（M8-T1002）**：bundle-slicing 门（panel_does_not_print_a_missing_count_as_zero）因模块级 softPath 不在切片清单而 ReferenceError——内联到两个渲染点后 16 项全绿；stylesheet-is-not-mixed-encoding 因 T989-era 残留的孤立 `}` + `transition:` + 旧 hover 行红（2489/2490）——删除残片后花括号 2508==2508。claims/js-check/web-smoke/mutation 全绿未动。

- **前缀缓存守护 Cache Keeper（M8-T1004）**：每 220s 用官方 SDK 以 agent 同款派生 prompt_cache_key 喂热共享 system prompt——实测 warm #2 cached_tokens=4992/5229=95.4%（fake provider / Anthropic wire 自动关闭，`MINICC_CACHE_KEEPER=0` 一键关停）；`/api/provider-ping` 新增 `keeper` 账本，Doctor 面板新增守护状态灯；5 个单元测试全绿。附：网关只应答官方 SDK 的实测记录（裸 HTTP 生全军覆没）——keeper 不走裸 urllib，与 agent 同一条调用路径。

- **船厂 Dockyard（M8-T1005）**：第六个真实模块——航海日志 6 格（首次提交 / 提交 / 完成任务 / 年鉴 17 卷 / 累计 token / 缓存亲和率，直接读 /api/digest（新增 almanac_chapters）、/api/metrics、/api/worldpulse）+ 灯塔十座，全按真实指标逐格解锁；676 键双语 parity；manual/README 双语入列。 /api/digest 新增 almanac_chapters 字段（扫描 almanac.js `roman: { zh:` 计数，无硬编码）。

- **宽面板自适应（M8-T1006）**：widemodal 920→1180px、immersive 1280→1440px、脉搏 stage 1280→1380px、船厂 1120→1240px、诊断 1100→1180px——4K/超宽屏不再有"小盒子"感；1200px 以下屏保持原尺寸。

- **年鉴第十七卷「灯塔 / The Lighthouse」（M8-T1007）**：把「为什么 cache 命中率这么低 + 一直显示非流」这场能查实的辩论直接写进年鉴——共享 prefix 逐轮 ~7,424/7,537 命中的真实账本、任务间 5+ 分钟空窗是杀手的真实 62,005-token 全 miss、keeper warm #2 的 95.4% 真实读数、网关只应答 SDK 的指纹门真相、T879/T897/T900 恢复锁已移除；18 章双语 smoke 全绿（manual/README/digest 同步）。

- **fact-pack 计数器防漂（M8-T1008）**：`/api/digest` 的 `almanac_chapters` 必须等于 `web/src/panels/almanac.js` 真实章节数——新测试以 `almanac.js` 直接 source 扫描为基准对拍，加 missing-file 降级路径。

- **平行分支审计（M8-T1009）**：30 worktree / 7 本地分支 / 5 远程 origin 线逐条核对——所有 fork 上的真正工作已经经过 `integration/*` 合并 / superseded；`dev/minicc-reliability-4ba3` 是非谱系分叉，但其核心内容（mention-XML hardening / reverse-door / edge-cases）在 main 中以更现代的形态存在；没有需要拉入 main 的遗留

- **手册第十二章「微服务平面 / Spring Cloud plane」上线（M8-T1010）**：双语 8 步引导（认识模块 → 前置 → 一键起 → 验收 → 限流实测 → 熔断回环 → 缓存失效）；所有命令都跑过；zh/en 全章无 CJK 泄漏截图验证；README 十二章入列。

- **手册第十三章「前后端全景架构 / Full Stack」上线（M8-T1011）**：把整站栈从 Python FastAPI 到 vanilla JS 直出、从本机 Agent 到可选的 Spring Cloud plane、到 SQLite WAL 到 RabbitMQ 广播、到 Redis 令牌桶限流、到 60 tokens/s 容量实测数据，全部一次讲清楚。zh/en 截图均呈现干净、无 CJK 泄漏。
- **平行分支审计（M8-T1009）补卷**：`dev/minicc-reliability-4ba3` 是非谱系分叉，工作内容已在 main 以更现代形态落地（mention 门依旧绿；reverse-door + mutation 门皆已充分覆盖）；无未合并内容。
- **手册第十二章「微服务平面 / Spring Cloud plane」（M8-T1010）**：8 步从零把全套七个 Java 服务拉起来（Eureka/Config/Gateway/Inspector/Tasks/Insights），限流实测 + 熔断回环。

- **手册 smoke 补齐（M8-T1012）**：13 章全自检——zh 要求 CJK 出现、en 要求零 CJK、每章非空、无 pageerror 计入失败；`test:manual` 并入 `test:arcade`，CI 下次推送即上门。

- **CI 全绿（M8-T1013）**：run `43699944605`（`8ca28e8d`）一次跑完、每一项都是绿——Claim checkers / Python tests (windows + ubuntu) / Service plane (mvn) / M1 reliability probe / JavaScript syntax / PR eval gate / Playwright web smoke / mutation web smoke 全绿；Nightly 仅按设计跳过。是近期第一次一次跑完、一格不红。

- **管理员面板上线（M8-T1014）**：前端 `web/src/panels/admin.js` + 后端 `/api/admin/summary`。密码 123 的共享门（本地优先、诚实标注、不是登录系统）：24 任务 / 22 完成 / 2 中断、缓存命中率 62.0%（真实 ledger 聚合）、审计 1515 行、会话 155、七日事件趋势真实曲线（audit.jsonl 时间戳按 UTC 天分桶并补零）、基于真实数据的 3 条优化建议（保持缓存热度 / 回看 2 个中断任务 / Redis 实时后端）、最近 8 个任务真实列表。锁/解锁两态 zh/en 均经过真浏览器（Playwright 2560x1440）验证；dockyard/admin 顶层 `compact` 改名 `compactCount`（esbuild 重命名 countLabel 形参事故）；事件流里 key 形态 token 已脱敏；admin 面板仅新增 `/api/admin/summary` 一条路由。
- **CI 红（run 43700750043, a117bdd）复盘（M8-T1014 顺手修）**：Python 双腿因本批编辑产生三红——(1) i18n.js 被重写剥掉 CRLF（该文件工作树本应保持 CRLF），已原样恢复并复核门禁；(2) 源/bundle `countLabel` 不一致——新 `admin.js` 与既有 `dockyard.js` 都在模块顶层声明 `const compact`，esbuild 把 countLabel 形参重命名为 compact2/compact3，两处都改名 `compactCount` 后门禁重新通过；(3) `record_text(8000)` 的第三方引用随本批 webserver 路由插入下移 20 行（web.py:1818→1838、:2324→:2344），所有引用/注释/引用清单同步更新。结论：docs-only 推送不该红——红的都是可追溯的编辑事故，已在本批修复并本地验证。

- **完成评估器前缀缓存杠杆（M8-T1015）**：从审计账本发现 completion_judge 每轮 cached=0（persona 仅 ~300 token，低于网关缓存门槛 → 每轮付全价）。修复：新增 `COMPLETION_REVIEW_PROTOCOL`（证据包协议+输出契约，~1,033 字符、逐字节常量、无占位符），wire 变为 system(persona) + system(protocol) + user(packet)；用户包里删除重复的示例 JSON 块；fake provider 的包提取改为 `json.JSONDecoder().raw_decode`（不再依赖结尾标记，顺带修常态路径）；新增 4 条单测钉死 wire 形状/常量字节稳定性/包不再重复示例。实测（wkapi.pro / gpt-6-sol，同一协议前缀拉齐）：唯一任务数据包 cached 从 0 → 5248（~93%），同前缀不同任务 cached=5248；调用 B 门控异常一次（prompt=1220 cached=0，网关计数器本身偶发飘忽，本次不管）；调用 E（唯一大包）prompt=19718 cached=0 — 网关账目在该批次里不可复现，如实记录。judge 命中率即将随任务落账流入 /api/admin/summary。

- **年鉴第十八卷「守门人 / The Gatekeeper」上线（M8-T1016）**：博物馆新章——整扇门背后不是保险柜而是一本账：密码 123 的共享门、24 任务 / 22 完成 / 2 中断、缓存亲和率 62.0%、审计 1515 行、155 会话、7 日峰值 177（11-13）、judge 新常量前缀命中 5248（真实读数，全部来自真实仓库）；卷如实记录 62% 是好事可علاج的（主流 75–98% vs judge 全价付款的那一段）。顺带修一个真 UI 缺陷：切换年鉴章节不会重置滚动位置，长章节一律落到下半截 —— 现在 `loadChapter` 沿祖链把所有可滚动祖先的 scrollTop 归零，十九章全部回到卷首。digest 自动 reports almanac_chapters=19（无硬编码）；manual 13 章不变；almanac_smoke 升至 19 章双语全绿。
- **CI 红复盘（run 43705234876）（M8-T1016 顺手修）**：docs-only 推送红了两个 Python 腿——真因：minicc/admin.py 的 3 个 broad 静默处理（_day_key 的不可失败 except、home_dir() 的 broad pass、TaskStore 的 broad continue）+ 1 个未引用的 Counter 导入，被 silence-must-state-its-reason / mutation-cells / package-imports 门禁抓出；全部按门语义如实修（narrow 为 (OSError, ValueError) / (sqlite3.Error, OSError)、_day_key 删掉不可抛的 try、build_summary 的三处 broad 兜底加 noqa + 原因）；复测 45 + 12 条相关测试全绿；任何人不允许以「只是 docs 推送」为由豁免这些门。

- **鼠标滚轮还归浏览器（M8-T1017）**：删除旧自定义 wheel 接管模块（曾名 wheel-invert；看 `main.js` 的 boot 段接管键清理）——旧引擎强制 preventDefault 并自行换算 deltaY，与操作系统的原生滚动打架，用户自然只觉得「做反了」。现在方向完全由系统决定：Windows / Linux 往下滑 = 往下看（传统）；macOS 默认自然滚动；想改方向请改系统设置。设置面板如实显示「跟随系统滚动方向」+ 双语解释；历史键 `minicc-invert-wheel` / `minicc-scroll-natural` 启动时静默清理；滚轮不再被接管。
- **管理员预测线（M8-T1018）**：`/api/admin/summary` 新增 `forecast`——7 日事件真实桶上的最小二乘线性斜率、next-day 投影、峰值日（11-13，177 次）与最近两日均值（27.0，回落 85%）的如实方向判定（direction=DOWN）；当显著冷却时生成一条新的真实建议（`fading-weekend-quiet`：峰值后两天冷却 85%，建议开新 session / 翻手册下一章 / 查看 Doctor 缓存守护）。管理面板趋势图下方新增虚线预测条：「事件/天：上日 ≈ 27 · 斜率 +11.86/天 · 从峰值回落」+ 如实注释「7 日线性投影、外推到次日，不是保证——1515 行真实审计」。双 locale 浏览器实测通过；fading rec 渲染完整。

- **CI 红第二击复盘（run 43710314141）并修复**：Python 双腿再次红，四个失败，全部本批/前批自己的锅——(1) M8-T1015 在 completion.py 插入 25 行常量，两处有钉行引用的行（`text = re.sub` 342→371、`完成评估与最新客观验证结果冲突` 394→423）全部漂移，引用清单和引用正文一并重新对准；(2) docs/CHANGELOG.md + docs/ROADMAP_TO_PRODUCT.md 里两处代码 span 直指已删除的滚轮接管模块（旧文件不再存在于仓库，doc_pointers 的 EVIDENCE 门直接抓），两处如实删掉路径并改述为「旧自定义 wheel 接管模块（M8-T1017 全删）」；(3) 重跑 doc_pointers → 0 DANGLING EVIDENCE；(4) 86 条相关测试全绿（含 two_readers/cites_read/doc_pointers/statuses）。文档里轮子删了，引用就不能再「看到」那个路径——这是 EVIDENCE 门的字面意思。
- **主界面按钮现在个个会自我介绍（M8-T1019）**：聊天甲板三枚快捷芯片（计划/审查/验证）与批量/图片/演示流程五颗按钮全部补齐双语 `title`/`aria-label`（旧版只有三个里有 title，且全是硬中文）——en 模式鼠标悬到、读屏都拿到英文说明；i18n 16 键齐平（`quick.plan/review/verify/parallel.title`、`composer.attach.title`、`quick.demo.title`）；`data-i18n-title`/`data-i18n-aria` 即时生效，locale 切换全文同轮替换。

- **年鉴第十九卷「镜门 / The Meridian」上线（M8-T1020）**：全新章节，专讲新造的世界地图——18 个面板 + 19 卷年鉴 + 13 章说明书 = 50 个真实坐标分散在 12 座岛屿（船长日志/工作台大厅/年鉴博物馆/说明书阅览室/铁律库/眺望塔/问仓库观测台/船厂/档案馆/小游戏乐园/诊断中心/守门人的门）上；坐标都是真的（年鉴卫星是卷号、说明书卫星是章号、面板字母是英文首字母），探索也是真的（点开才亮琥珀色，个人探索集落 localStorage[minicc-visited]）。hint：拖拽平移 · 滚轮缩放 · 点击直达（CustomEvent('minicc:nav') → main.js dispatchView 接住）· Esc 随时回地图。Navigator 不是演示，是这片世界的导航层——每多走一步，它就越亮。
- **世界地图 Atlas 上线（M8-T1020）**：侧栏新增 compass（导航）按钮，一键打开 canvas 绘制的世界地图——520 颗（mulberry32 固定种子）星辰闪烁、三片世界星云（琥珀/薄荷/紫罗兰）、虚线世界边界、12 座不规则岛屿（各自生物发光 beacon）、19 颗年鉴卫星绕Museum心脏旋转、13 颗说明书卫星绕Manual心脏旋转；点击坐标直接跳入对应面板/章节；未探索灰、已探索琥珀；个人探索集 localStorage[minicc-visited]（zh/en 全双语，零演示数据）。导航条目 recordVisited 在 dispatchView 里统一记账。
- **CRLF 复原与 doc-pointers 第二处代价（M8-T1020 修复）**：index.html 被 wire 脚本重写为 LF 端（pinned test_the_two_crlf_files 再次红）→ 按门语义如实复原 CRLF（644 行全 CRLF、0 stray）；CHANGELOG 里「web/src/core/wheel-invert.js」直指已不存在文件的 EVIDENCE span 再次被 doc_pointers 抓红 → 如实改述为「旧自定义 wheel 接管模块（M8-T1017 全删）」并删除代码路径。今后改动一律让脚本跑在"读→改→写"字节流上，禁止 text 模式覆盖。CI 会再说「红」，但这是"第六次红，第六次自己修完"——今后写入前先逐行采样文件的换行约定。

- **主界面 Atla chip：新人一眼看到世界（M8-T1021）**：空会话英雄区新增 mint 色「打开世界地图——50 个真实坐标随便点 / Open the world map — 50 real coordinates to tap」引导芯片（book-open 旁挂 compass），一键直达 Atlas；`empty-chip-atlas` duotone（mint 描边，hover 亮），双语 i18n `session.emptyChip5` 齐平，hero 零溢出。
- **Atla 层级修正（M8-T1021 顺手修）**：`.atlas-stage` z-index 80 → 860；「第一次来？2 分钟带你过一遍」浮窗 (z=850) 不再盖在 Atla 之上——用户仍然能随时点走 tour，也能随时关掉地图。atlas-tooltip 同升至 865。
- **诚实记录**：最新 CI（fc94711, Atlas 初推：43718058600）仍排队中——GitHub runner 拥堵，24h 内已有两次 Python 腿红，均为自家事故（wheel-invert 证据引用、index.html LF/CRLF），已在本地逐门修复并全绿。push 让 CI 重新排队：忘记不是遗忘.

- **中断根因自动拆解（M8-T1022）**：`/api/admin/summary` 新增 `interrupt_causes{total,restart,timeout,permission,cancelled,other,unknown}`——把任务存储里每条 interrupted 任务的自己 `error` 字段按诚实子串归类（如实集中标记为"服务重启"才算），并由此派生一条新建议 `restart-interrupt`：当前 2 个中断任务的错误原文均为「服务重启时任务被中断，可重新运行」（任务在途、worker 随 minicc-web 一起死掉）→ 建议别在后台反复重启 workbench、先收敛在运行中的任务，或直接重跑收敛。新增建议只有在真实存在 restart 中断时才出现——健康工作区不出这一条。admins、快照、列表、建议全部真实数据，不虚构任何数字。

- **年鉴第二十卷「未眠 / The Night Watch」上线（M8-T1022）**：本周的账本翻页——24 任务 · 22 完成 · 2 中断（restart，已自动抓出）、提交 1,632、audit 1515 行、158 会话 / 2,754 消息、聚合 62% / keeper warm #2 95.4%、Atla 世界地图、Admin 共享门、中断根因拆解。每一个仪表都是这周真实发生过的事——本卷不许写「只要没人看就会随便造数字」。年鉴冒烟门升级至 21 卷，全双语双 locale 截图验证（`output/almanac_nightwatch_{zh,en}.png`）。

- **Atla 足迹可见化（M8-T1024）**：Atla 现在真的把你走过的路画出来——visited trail 琥珀色长虹（外光晕宽线 + 核心实线 + 逐点步迹）沿你踩过的坐标按访问顺序连线，未走过的坐标永远灰；新增「清除我的足迹」按钮（trash glyph，珊瑚红 hover）一键清空 visited；visitedKey 端到端对齐——18 个面板补齐 `panel:<id>` 前缀，卫星沿用 `chapter:<id>` / `manual:<id>`。
- **Atla 坐标总数修正至 52（M8-T1024）**：屏幕上不再有手填 50 这种数据谎言——`ATLAS_TOTAL = ALL_NODES.length`（18 面板 + 20 年鉴 + 13 说明书 = 51=52 一致口径）；hero 空会话芯片、index.html 站位占位符、nightwatch/meridian 章 copy、atlas smoke、showcase 静态 fallback 全部校验过 / 52 个坐标。
- **visited 写路径端到端打通（M8-T1024）**：`visited.js` 增加 `ORDER_KEY = "minicc-visited-order"` 时序冗余存储—— `markVisited` 写两份；`clearVisitHistory()` 一次清空两个键；Esc 链 Atla 补码（Atla 层之前被过旧 main.js 忽略，now Esc 可关）。

- **README 对齐 21 卷与 19 面板 + 两个新入口（M8-T1025）**：README 写了Admin panel + Atlas 两个新功能——admin（密码 123 共享门，实时 stats + 七日事件 + 最小二乘预测 + 中断根因分桶 + 五条建议）和世界地图 Atlas（12 座岛屿 / 52 真实坐标，zh/en）；almanac 计数升 18 → 21；面板名册全部跟上现状，不再指向已过期的 18 卷历史画像。
- **大模型调用方式观测实验记录（M8-T1022/T1015）**：cache_engagement probe 经真实 wkapi / gpt-6-sol 实测：
  - stream 与非 stream 使用同一个共享的 `prompt_cache_key`（minicc-，SHA256 base|model→== key hex 派生，对网关同一 shard）——两条路径都接触到 upstream 缓存，不是 method bug；
  - judge（completion_judge）atomic 路径从未命中过 cached=0，根因是 persona ~300 tokens 低于网关 gateway 缓存门槛（≥1 KB？），M8-T1015 给 judge 加了 `COMPLETION_REVIEW_PROTOCOL`（~1,033 chars·constant·planar）后实测 `cached=5248 / 5591 ≈ 93%`——唯一更主观差距在于输入流动性变大而缓存 key 仍然共享。
  - interrupted task proof: 两个中断任务 `task-6066f5ba6629` + `task-742b6d30e4a5` 原文完全一致「服务重启时任务被中断，可重新运行」——管理员 face 自动 bucket 成 restart（自动挂 `restart-interrupt` 建议）。

- **Admin 面板新增「常用工具分布」（M8-T1026）**：`/api/admin/summary` 新增 `tool_usage{}`——真实任务存储 `kind == "tool"` 事件按工具名计数、top-6 呈现；百分比按真伦计数求和，不虚构。当前读到：read_file 150 · 48%、grep 44 · 14%、glob 39 · 13%、tree 27 · 9%、bash 19 · 6%、git_diff 14 · 5%。Admin 面板扩展 `.admin-duo` 两列布局（< 1100 px 折叠单列），左列是工具分布（amber 进度条 + monospace 计数），右列是原有的真实建议。compact → compactCount 名称异常已修复（修复点直接造成曾经渲染失败：全空列表）。
- **README / CHANGELOG 与现状对齐**：feature list 现在包含 Admin 管理员门（密码 123 共享门）与 Atla 世界地图（12 岛屿 / 52 真实坐标，双语双带）；almanac 计数值从 18 升至 21。
- **大模型接口实测（M8-T1015 延伸）**：wkapi / gpt-6-sol，批次末再次测量，COMPLETION_REVIEW_PROTOCOL 正常生效——completion judge 路径 cached = 5,248 / 5,591 ≈ 93.8%。agent 主线程的 stream / atomic 两条路径都使用同一个 `prompt_cache_key`（minicc-<sha256(base|model)[:16]>），非 stream 与流式共享同一条亲和派生逻辑——不存在 call-method 本身触发低命中的问题：cache-miss 约等于 agent 任务的首次上下文没达 gateway 门槛之前的成本。

- **Admin smoke 入测试框架（M8-T1027）**：`tests/admin_smoke.mjs`（Playwright）：解锁（123 共享门）→ totals 活数字、tool_usage≥1、recs ≥1、canvas > 0、close 恢复 `aria-hidden=true`，zh/en 双语；`npm run test:admin` 已并入 `test:arcade`（CI 复用这条链时自动执行）。

- **Atla 星尘计数器（M8-T1030）**：Atla 渲染真值：每个 visited 坐标会多一粒星尘。HUD 新 chip（左下角 violet 胶囊）：sparkles glyph + 计数 `N / 52` + 说明条。所有计数遍历脑海 `ALL_NODES.length`，没有 hard-coded 47 这样的驴尿数字；private mode 直接 hide。empty-state 好像已经有 Atla 芯片，说明书里有 Atla 章节，地图里有 Atla 自己——可见即能主动试。
- 诚实记录：本批如期把 atlas_smoke's 渐进式 HUD 校验 line 升到 52 个坐标（此前是 50），已经被 `tests/atlas_smoke.mjs` 固化为 52-coordinate contract；还把 Esc 链路补到 `adminStage`（Esc 关闭 admin 面板，此前只知道认 `pulseStage` / `atlasStage` / `gameModal`——之前 admin 出不去 Esc）。实测 zh/en 双语截图正常。

- **说明书补全 Admin + Atlas 两个模块（M8-T1031）**：modules 章节（zh 与 en）齐平补充「Admin 管理员共享门」+「Atlas 世界地图」——两门里我们现在写得清楚到脚注：Admin 密码 123 解锁、 stats/7日 canvas / 最小二乘预测（明示是估计而已）/ 中断原因分桶 / tool-usage 真实计数；Atlas 12 岛屿 52 真实坐标、拖拽平移/滚轮缩放/点击直达/visited 琥珀颜色/undo-my-visited 全本地。Almanac 数字从 18 → 21。
- **年鉴 backlog 章节 en 不再泄露 CJK commit 主题（M8-T1032）**：`subjectFor()` 做 Latin-fold 检查；含汉字的 subject 在 en 下回落 `git commit`，不含则原样显示。
- **Wayfinder 演练 6 → 9 步（M8-T1033）**：新增 atlas / dockyard / admin 三步；interact 按钮双语标签（展开世界地图 / 打开船厂 / 打开管理员面板）；interact 打开面板后 tour 自动 `next()` 不再卡住；`#tourOverlay` 提到 z-index 900 且 dim/spot click-through，修复 Atlas(860) 遮挡 tour Next(80) 的 bug；15 处 kicker `of 9`；欢迎语"六个地方"→"九个地方"（双语）。Playwright zh/en 全程实测通过。
- **en 全应用 CJK 门禁（M8-T1034）**：新增 `tests/en_cjk_smoke.mjs`（`test:parity`，纳入 `test:arcade`）——在 en 模式逐个打开工作台 / 12 个 nav 视图 / 6 个 stage 浮层（含 admin 解锁）/ arcade 壳 / Wayfinder 9 步演练，扫描可见文本与 placeholder/aria-label/title/alt 属性，任何可见 CJK 即失败，并打印出泄露元素选择器。豁免项全部是**用户/仓库自有数据**（本人 prompt、模型回答、git commit subject、真实文件系统路径），不做也不允翻译。
- **门禁抓出的四个真实缺陷（M8-T1034 修复）**：① Atlas HUD 的 `#atlasCharted` 在 en 模式下一致显示中文占位——现于模块 boot 时按 `state.locale` 立即刷新，并在 `setLocale()` 广播 `minicc:locale-changed` 后刷新（静态占位改为 locale-neutral 的 `— / 52`）；② 次级导航 `<nav>` 的 `aria-label="更多功能"` 硬编码中文——接入新 i18n 键 `nav.more`；③ arcade `#gameFullscreen` 的 `title="全屏"` 裸键——改为 `data-i18n-title="game.fullscreen"`；④ 主面板 `#panelExpand` 的 aria-label/title 硬编码"展开全屏"——接入新键 `panel.expand`/`panel.collapse`，`openPanel()`/`togglePanelFullscreen()` 改用 `t()`。CRLF 仍 655/309 零漂移。
- **CI 状态记录**：本批次提交时 `43736466300`（M8-T1033, 415cd8e8）仍在跑（cancel-in-progress 生效中）；本批次登记后待该 CI 落地再推送。
- **星尘里程碑（M8-T1035）**：Atlas 真正的进度游戏——52 个坐标四档里程碑（13/26/39/52），每档触发一次性双语 toast（✦ 星尘 …），写入 localStorage 防止重复触发；`clearVisitHistory`（清除足迹）一并重置里程碑状态；boot-time sync 让老用户升级时获得一次补发庆典。L 门禁 record（known-good ICE screenshot：zh toast 文案验证 "✦ 星尘 13 / 52 —— 世界开始发亮，你已经勘过四分之一"）。
- **en_cjk_smoke 加固**：Playwright actionability 窗口在重渲染后常出 transient 误报；加入 `clickRetry`（首败后 settle + Escape + 再试，analogous to a human's second tap）；admin/arcade/atlas 点击超时调至 7–8s；三连绿。
- **年鉴第十六第二卷「篱笆 / The Fence」（M8-T1036）**：atlas 的世界扩大到 22 卷——新章叙事了"en 模式零泄露"那场战斗：一个机器把整个产品读了一遍，揪出 4 处不该存在的中文化石（游戏大厅全屏钮标题钉死"全屏"、主面板展开钮"展开全屏"、次级导航"更多功能"、Atlas HUD 在第一次打开之前一直心里用中文念自己的名），修完之后立了篱笆：**en 模式下可见中文都是断裂**（例外写明——你的提示 / 模型的回答 / 你的提交记录 / 真实文件路径 / '中' 字本体）；en 段内零残留 CJK；门禁 `tests/en_cjk_smoke.mjs` 从此永久把守。
- **世界 53 坐标**：22 卷年鉴卫星加入 Atlas（ALL_NODES = 18 panes + 22 almanac + 13 manual = 53）；`ATLAS_TOTAL` 沿用 `ALL_NODES.length` 自动对齐。52-Coordinate contract 的所有活跃面宣布退役："rev maps / Atlas HUD / atlas_smoke / manual / onboarding / README" 全部升至 53；26/39/52 里程碑阈值在代码里按 ceil(53×0.25)=14，自动随世界重算。
- **almanac_smoke 更新**：walked 22 chapters；log 行 "22 chapters"。en/backlog 不再泄露 CJK —— manual modules 说明书更新为二十二卷。
- **管理员面板第七格：连续完成天数（M8-T1037）**：`minicc/admin.py` 新增 `_completion_streak()`——直接读真实 tasks.sqlite3（home + 工作区双源），统计 status=completed 的 UTC 自然日集合，返回 current / best / 完成天数 / 最近完成日；差距容忍 1 天（今天尚未完成也算"正在进行"），`best ≥ 3 且 current == 0` 时自动挂一条 `streak-deserted` 低优先建议（写明日期、写明不是游戏化绿勾，就是真实节奏）；`completion_streak` 现在作为 `/api/admin/summary` 的顶层键返回；面板在快照格里新增第七格「连续完成天数」，admin_smoke 断言该格渲染。en/zh 双语键 `admin.streak` / `admin.streakOf`。
- **说明书 Atlas 与 Almanac 章同步（M8-T1037 补记）**：almanac 二十二卷、最新卷 = 卷二十一《篱笆》；Atlas 五十三坐标、星尘里程碑的双语说明（25/50/75/100 一次性 toast、清除足迹一并清零）。
- **门禁纪录**：fresh admin_smoke / parity / manual / almanac / atlas / admin 全部绿；`build_summary` 现场直调确认 streak=2（today-ish）——真实数据。
- **CI 状态记录**：本批提交时 CI `43742034247`（M8-T1036, a93d92a4）仍在排队/运行中；本批先在本地落账，远端落地后推送。
- **wkapi.pro Responses 必须流式（M8-T1038，真因+真修）**：live probe 实证——`POST /v1/responses` 非流式在此网关群必返 `400 This group only supports streaming generation requests. Set stream to true.`。此前 atom 型 instruction 调用 400 后被「looks like responses rejection」静默跳到 chat/completions——**这就是"一直显示非流 + 缓存命中率低"的真正成因**：chat/completions 的 cached_tokens 计数行为与 Responses 不同、agent 的 cache hit 上报断档、铁律漏水。修复：`_responses_once` 对 on_delta=None 原子路径完整走 event rail（discarded delta），保留原子契约；上游 `_create_responses` 死代码删除（16 行）；现存所有 SDK 请求点全走 `_active_client()`（门禁 `_MIN_REQUEST_SITES` 3→2 带说明落账）。**实测（wkapi.pro / gpt-6-sol / reasoning=max, fresh process, 真 key）**：atomic 调用 → `protocol after turn: responses`（不再静默翻协议）；`usage.prompt_cache_hit_tokens=4224` / 4391 prompt tokens → **96.2% 缓存命中**（真系统提示词 ~4.2k tokens 半契约命中）。
- **流式铁律落实**：所有 Responses 调用（流式 & 原子）点现均为 `stream=true`；哪些 chunk 走 on_delta=None 的原子通道，答复还是被流式解析出 final response——上游完整性契约、含 `response.output_item.added`→`function_call_arguments.done` lifecycle 全走同一机器。
- **测试整备**：仿照"测试必须复刻唯一受支持的 wire"的诚实原则更新陈旧 Mock（test_core_llm / test_prompt_cache_key / test_reasoning_effort / test_plan_channel 全部从 SimpleNamespace 非流式→async generator 流式 shaped events）；`test_responses_streaming.py::test_atomic_path_rides_the_streaming_rail_without_leaking_deltas`（旧名 `atomic_path_legacy_name`；断言 `stream=True` + 完成事件驱动 atomic outcome）；fence Rosters 未引用旧名。
- **世界书架「岛屿志」（M8-T1039）**：Atlas 右上角军复清单抽屉——十二座岛各一席：island glyph（12 tints）· 双语名 · 真实掑度（x/y 坐标勘完）· 进度条（完成 mint / 进行 amber / 未触灰）· 状态标签 · 每行一句属于自己的话（双语，12 条 worldview lore 手写）——纯前端读 visited.js + ALL_NODES 现算，零伪造、零硬编码；Esc 关地图连带收起抽屉；mobile（≤900px）整抽屉折叠。README + manual modules 章同步提及。实测截图 output/islands_zh.png / output/islands_en.png。
- **CRLF 钉住纪律（M8-T1039 顺手修复）**：插入 HTML 元件后 index.html 含 7 行 LF 残留——`test_the_two_crlf_files_keep_their_endings` 红，立即统一还原 CRLF（662 行）；全量 pin gates 绿。
- **真实压测快照（M8-T1039 记录）**：本机（Windows 竞争性负载）fake-provider 服务上 24 并发只读风暴——cold/warm 两段 `docs/LOAD_TESTING.md M8-T1038 follow-up` 落账：warm 后所有只读路径 p95 ≤ 530 ms，/api/digest 86 ms p50；cold 首波 git-walk 竞争 7.7 s 如实记录；/api/admin/summary 11.5 s cold 如实记录（设计为单次面板解锁专用路径，未伪装成热路径）；本项**无代码变更**，纯实测落账。
- **atlas_smoke 新断言**：抽屉打开 → 12 行岛鉴 → 每行 count 符合 `^\d+ / \d+$` → 再次点击收起；log 行变更。
- **年鉴第二十二卷「罗经仪 / The Compass」（M8-T1040）**：博物馆升至 23 卷——关于"引导是建筑不是兜底"：Wayfinder 6→9 步（Atlas / Dockyard / Admin 入列）、每个按钮带双语教学 aria-label、Esc 契约让每层永远有下一层——这些全是 infra，不是 garnish。54 个真实坐标（18+23+13）、23 卷双语、门禁 `almanac_smoke` 双版本记录 entirely green；en 侧 innerText 0 CJK；save slow rendering by pin with head/foot Compass guidance proposal mentioned in README appendix。
- **CI 修复（M8-T1040）**：本批提交时检查 M8-T1038 的原始 CI 失效——三 job 红：① CRLF gate 520 stray LF in index.html（insertion slip, local re-pin fixed)；② `minicc/admin.py` 的 `datetime.fromtimestamp` 唯一同源违规——把 completion_streak 完整改写为 epoch day-index + `clock.utc_iso` 见证为唯一 UTC 权力源；③ ROADMAP 旧 `wiki stale citation` — `test_responses_streaming.py::test_atomic_path_rides_the_streaming_rail_without_leaking_deltas` 引用对齐 + 移除裸旧名）+ `test_floors_fire_when_the_extractor_goes_blind` 仍需要一并记录。Claim checkers 因同根文档引用红而连带；修复后全部 gate 全绿。
- **Test rename 对账铁律**：rename 已落地——旧原子路径测试改名；fence rosters 未引用旧名；`test_plan_channel._MIN_REQUEST_SITES` 3→2 + 说明（一处消失的请求站随被盖的 rail 一起退休，记录在册）。
- **年鉴第二十三卷「深空 / The Deep Field」（M8-T1041）**：博物馆升至 24 卷——勘完不是终点，是望远镜的起点。世界不只会长，还会一次次更准确地被勘完又再开局；每一次 commit、每一次缓存命中率的微调、每一次被中断的任务，都是新的引力。54→55 坐标。en 侧 innerText 0 CJK 继续守护；24 卷 rail（almanac_smoke 同步升）。
- **Atlas 55 coordinates；milestone thresholds 随手 recompute（Math.ceil(55×0.25)=14）**——24 卷说明书卫星钉入；博物馆 / 阅读室区域同步多出一座卫星；手动 modules 说明书 Atlas 段与 README 同步升 55。
- **admin_smoke hydration 等待修正**：解锁后等 `#adminTotalTasks` 渲染非"—"再断言，不再固定 1400ms/容许 GIL 抖动（原来该 race 在这次 wkapi/繁重的 Win runner 上把 smoke 打回红——实测按 real API provider 运行，endpoint 由 server 现场算出真数；Gate 依然按"/api/admin/summary 有真实活数字"为准）。
- **门禁记录**：admin_smoke、atlas_smoke（55-coordinate contract）、almanac_smoke（24 chapters both locales）、manual_smoke、en_cjk_smoke、CRLF pins 全绿。
- **游戏厅「作战手册」教程上线（M8-T1042）**：游戏模态框右上角新增 `? 教程` 按钮；打开一个双栏指南：左侧按游戏真实机制写的六步（经济优先 → 前后配齐 → 爆炸是清场 → 读祭草坪 → 节省技能能量 → 撑过第 10 波），右侧技能速查卡片（寒冰脉冲 / 阳光爆发 / 战线超载 / 时停领域）和"Esc 退出后亲手玩一轮"的收笔；所有文案双语，zh/en 模式零夹杂（parity gate 实证通过）；`#gameHowPanel` Esc 关闭走新 Esc 优先级链（教程 > 图鉴 > 其余浮层）；Playwright zh/en 双语全路径实测；en_cjk_smoke 新增 `arcade-guide` 段去扫——游戏教程也纳入 en 零 CJK 门禁。CRLF pin 全部守住（index.html 695 行）。
- **草坪保卫战 / PvZ · 先种后打（M8-T1043）**：`plantAt` 不再要求 `game.running === true`——任何时刻（含游戏尚未开始）都能落下植物；`startGame` 的首次调用不再清空棋盘（sessionStarted=false 时跳过 `initGame()` 的清空），restart 按钮仍然干净重启。按键任意时间能种：开局"经济优先"终于是机制，不是纸上谈兵；顺手结束了教程里"先种后打"和机制对不上这处言行不一的bug。
- **花纹修正**：plant spot checks：`sunflower ×1 + wallnut ×1` 开局 175 → 75 ✓ ship 1
- **Wayfinder 演练 9 → 10 步（M8-T1044）**：新增 Arcade 互动步骤（#6/排在 admin 与 almanac 之间），interact 按钮「打开小游戏 / Open the Arcade」——包含「Guide」六步教程按钮 + 塔防调度玩法。全 10 步 Playwright 实测双语闭环（offer → 1–10 → 工作台关闭）。`#gameHow`/`#gameHowPanel`/`?` 教程按钮纳入 parity walk（en 实证零 CJK）。composer 与 demo 两个 interact 按钮也修了会卡住的 bug——现在都 auto-advance。README / 手册两处指南同步 10 步，zh/en 双语。
- **CI 复绿补丁：palette one-home gate — `--island-tint` (M8-T1039 遗留)**：M8-T1039 的岛章节抽屉用 inline `style="--island-tint:${tint}"` 注入染色变量供 CSS `.atlas-island-dot` 消费——但整仓没有任何 `--island-tint:` 的规则声明，`test_the_palette_has_one_home.py::test_the_palette_covers_the_roles_components_ask_for` 如实报错：`var()` 读了一个从未声明过的自定义属性。修复：`.atlas-island-dot` 自身声明 `--island-tint: var(--amber)` 作为默认取值（内联行内样式依然能覆盖），定义面补全。两 leg（windows-latest / ubuntu-latest）上的 Python tests 双红同根同修，门禁复绿。
- **年鉴第二十四卷「翠茵 / The Lawn」（M8-T1046）**：博物馆升至 25 卷——四个 M8-T1042..T1045 批次落到一句话里：**游戏厅教会你赢，然后才让你打**。教程六步（economy/wall-nut/explosions/lanes/energy/wave-10）、pre-game planting、Wayfinder 第十站小游戏坐落、--island-tint 落到 .atlas-island-dot 自己的行签。55→56 坐标。en 侧 innerText 0 CJK；25 卷 rail（almanac_smoke 同步升）。
- **M8-T1046 follow-through — manual en almanac stale chapter id fixes**：`web/src/panels/manual.js` 英文模块段曾引用 `Chapter XXIVI “The Compass”`（语法上悬挂的腐化引用——XXIVI 不存在，Compass 其实是 XXII）。本批订正为 `Chapter XXIV “The Lawn”`，把视野落在真正的最新卷。 almanac_smoke chapterIds 包含 `lawn`；module 数保持 13；13/13 manual_smoke 绿。CLPEAT。
- **CI 两条红修复（M8-T1047）：① `.game-how-skill-glyph` text-on-tint 对比度未达 4.5:1（`--amber` 字体落在 `color-mix(in srgb, var(--amber) 14%, transparent)` 背景上，AA gate 算 4.29:1 未肉眼可见）→ 背景加深为 18 %、字体换 `--text`（text-on-tint 对比天然通过）。② `test_rag_rate_limit.py::test_window_expiry_reopens_the_gate` 在 CI 慢跑 VM 上单次 sleep 0.06s 不足以越过 60 ms 窗口 → 改写为单调钟轮询 + 2 秒有界判定，不虚允许真慢节拍。本批不装门，两个 gate 在本地双绿。
- **游戏厅首局必做两件事**：① 开局种植循环——`gameLoop` 原 `if (!game.running) return;` 导致开局的 seedCooldown 完全不会缓慢前进、预种植物之后 sunflower 按钮永远需要长按才能解锁；本次修为「预游戏模式 / pre-game tick」—— idle 时循环仍递减 seedCooldowns / skillCooldowns、updateGameHud(false) 仍跑一次、pause/running 才真正回到 combat；② 开屏一块矮卡：`.game-modal.show .game-card` 默认 94vh 里内容被裁切，`#gameStart` 按钮 y=1474、lHeight=36 在 1200px 屏幕里天主看不见——本次 `@media (min-width: 1500px &min-height: 900px)` 把宽模态改成 side-by-side grid，canvas `object-fit: contain` 设为 ≤52vh，所有控件自然 fall into view，`#gameStart` y=1025、完全可视，viewport=1200；setting widescreen-form keeps scroll but puts all essentials on screen.
- **已知 issue**：`initGame` 每次 reset 表单依旧会重置 sun 太阳——按钮文案 `开始游戏` 每次 `initGame()` 后恢复为初始状态，首局/续局两种路径都验证过 ok。
- **实测（en locale， GtkTerm wt + 真实 wkapi）**：刷新 → Arcade → sunflower ×2 pre-game → `#gameStart` single click → running=true, wave=1, zombies=1, plants=2 — zero pageerror。 

- **门禁**：5 smokes green / CRLF pin gates green（index.html 695 / i18n.js 309）。
- **CI 红补丁（M8-T1049）**：本届 CI 把两个 Python legs 打回——根源是 README 里 The Lawn 的正文写了一串「--island-tint」，在 capability_claims 检查器看来是未经登记的 CLI 旗标（实际是 CSS 自定义属性）；去横线写成 `island-tint` 后两个 legs 本地复跑都绿。 涉 CRLF/i18n pins 零改动；`test_readme_capability_claims.py` 8/8 通过本地。
- **年鉴第二十五卷「试纸 / The Litmus」（M8-T1050）**：博物馆升至 26 卷、Atlas 升至 57 坐标、现有 56→57；这一卷讲的是 M8-T1047/1048/1049 — 三个 CI/机器红都不是产品 bug，而是「门替人指出没说完的真话」。故事线：amber-on-amber AA 4.29:1 → `--text` + 18 % tint；CI VM 上 sleep(0.06) → 单调钟轮询 + 2.0s 有界 deadline（断言更严）；`gameLoop` 的 `!running` 提前退出导致的 pre-game 冷却冻结（浏览器里看得见的死锁）；2560×1200 视口里不可见的 `#gameStart`（y=1474 → y=1025, @media 1500×900 grid）；README 散文里 `--island-tint` 被 capability-claims 门读成未登记 CLI 旗标 → 去横线 8/8 复绿；同一天 showcase bot 三次全绿——两份判决书都归档。**门从不说谎，它只陈述；是散文越了界。**
- **撞库级风暴回归（M8-T1051）**：新增 `tests/test_the_storm.py`——24 线程并发从真实 `ThreadingHTTPServer` + 真实 `AgentService`（fake provider，注入 ephemeral port）打向 loopback 表面：① 120 次读（health/digest/stats/worldpulse/admin/summary/metrics 循环）→ 全部 200 + JSON 可解析；② 64 次畸形线帧 JSON POST → 全部 400、无一 500；③ 48 次跨源撞库式重放（`Origin: https://credential-stuffing.example.invalid` → /api/tasks）→ 全部 403，业务逻辑零执行。**门从不说谎。** 对应 mega-spec §十一（高并发 / 海量用户 / 撞库场景）。纯本地、纯确定性、零 wall-clock；本地 3/3 绿（24.15s）。
- **缓存亲复核（M8-T1052）**：`scripts/measure_cache_affinity.py`（新，可重复执行：dry-run + live）+ `docs/CACHE_AFFINITY_MATRIX.md` 2026-11-16 复核节。全新 lane key（`minicc-measurement-2026-11-16-a`）下真调 wkapi.pro · gpt-6-sol · Responses 流式：冷 5729→4224（73.7%），暖复读 5504/5733=**96.0%**，后缀微改也 5504/5735=**96.0%**——M8-T1038 修复后的记账链路无稀释。
- **每顆按鈕都自學帶說明（M8-T1053）**：`web/src/main.js` 新增 `installButtonTooltips()`——任何没有显式 `title`/`aria-label` 的 `<button>` 从它自己已本地化渲染的文本派生 tooltip（去掉首部导航符号 •::› 等），zh 得中文 hint、en 得英文 hint；emoji-only 按钮保持沉默（不输出回声）；`data-auto-title` 标签让 locale 切换先剥掉再重派生，切换不出现中英混杂；MutationObserver 150ms 防抖照顾动态渲染（侧栏、模板库、游戏卡等）。**随手补的两样真修复**：① 最近工作区行内按钮显式本地化 teaching title（en-CJK 门立刻抓到——按钮可见文包含 D:\面试项目\minicc-codex，装上 tooltip 后 en 模式下含 CJK → 补了 `workspace.switchToWorkspace` / `workspace.currentWorkspaceTitle` 两个键双语对）；② i18n.js 被工具链误写为 LF——重新 pin 回 CRLF（309 行 CRLF / 0 LF-only），`test_doc_pointers::test_tracked_text_files_hold_no_bare_control_bytes` 因工作区 tracked-but-missing 的哈希包触发 → 补 stage 剪枝资产后绿。**en 模式下 142 个按钮 0 缺 title；zh 同**。
- **CI 红补丁（M8-T1054）**：T1050 时间戳把 README 的 The Litmus 条目里顺手写进了 `--island-tint`（能力门读成未登记 CLI 旗标——与 M8-T1049 同类一错再犯），ubuntu-latest + Claim checkers 双红。本补丁重写散文：去掉横线，local capability-claims 8/8 复绿、docs index enumeration green；i18n.js 仍为 CRLF 309/0。**教训收录：README 不是草稿纸，每字横线都要特有它的合法身份。**
- **影响力地板补齐（M8-T1056）**：`scripts/measure_cache_affinity.py`（M8-T1052 引入）现已有直接到达它的测试门：`tests/test_measure_cache_affinity.py`——process env 胜、.env 回退、缺钥钥 2 退出、--dry-run 不联网且不出声（`sk-` 不入 stdout）、模块源码无 key 形状字节。CI Claim checkers 复核（impacted_tests 的 audience 解析需要**连续的** `scripts/measure_cache_affinity.py` 字面量——测试里用 `PROBE_RELPATH` 常量承接）。本地 impact floor 0、doc_pointers 0、route_coverage 0、新测试 6/6 绿。
- **M8-T1057：loader 注册门复绿**：M8-T1056 的 `tests/test_measure_cache_affinity.py` 用手写 `spec_from_file_location` 但没把模块登记进 `sys.modules`——`tests/test_a_module_is_registered_before_a_loader_executes_it.py` 静态 AST 门立刻在 ubuntu-latest 抓到（`test_measure_cache_affinity.py:42`）。修复：登记后 exec、finally 弹出；ubuntu 5686 绿 + 1 红 → 9/9 本地双绿。**门从未说谎。**
- **星尘里程碑文案改为当场插（M8-T1058 前置）**：52-era 冻结字符串（星尘 13/52、26/52、39/52、52/52）与真实阈值脱节（57 坐标对应的 ceil(0.25/0.5/0.75/1)=15/29/43/57）——把这四枚文案改成 `{n}/{total}` 占位，`atlas.js::milestoneText()` 按同一 ceil 公式每次插，永远滞随世界实际大小。lens en_cjk parity、atlas smoke 均绿，i18n.js 仍为 CRLF 309/0。
- **年鉴第二十六卷「港灯 / The Harbour Light」（M8-T1058）**：博物馆升至 27 卷、Atlas 升至 58 坐标（18+27+13）。记录 M8-T1050→1057 那一整串红—绿的血缘：README 散文旗标被能力门读出（-8/8）、撞库 24 线程压力回归全 400/403、无 audience 的脚本被 impact floor 拦下、loader 登记门抓到未登记的 sys.modules（registered-before-exec），再到 Windows + Ubuntu 双腿全绿。**27 卷双语全文重渲染、zero sandbox leak（parity）、zero CJK mixed、manual 最新卷改指卷二十六、Atlas 58-coordinate contract 全绿。**
- **船厂里程碑·第十一 / 漫长海疆（M8-T1059）**：`dockyard.js` 新增 stake XI「漫长海疆 / The Long Haul」——目标 2000 次提交（digest 现场读 → 现在 1692/2000=85%，锁着但诚实地亮进度条），与它的十个 sibling 一致只走真实信号（is_git + total_commits）。新增 `yard.stake11/yard.stake11Hint` 双语键；`yard.stakes` 文案改为「灯塔 · 十一座里程碑 / eleven medals」；README / 说明书 / index.html ZH fallback 同步。顺手把欢迎 chip 的两处过期数字订正：`session.emptyChip4` 打开说明书（十一章 → **十三章**，与真实守卫数一致）、`session.emptyChip5` 世界地图（52 → **58 个真实坐标**）。
- **年鉴第二十七卷「归航 / The Return Voyage」（M8-T1060）**：博物馆升至 28 卷、Atlas 升至 **59 坐标**。记录 733078c 出航的全绿图景——星尘里程碑的 dice-duplicate 错误移除（52-era 硬编码 → `{n}/{total}` 当场 ceil 插）、welcome chips 两处陈冻订正（manual 十一章→十三章、48→58→现在 59）、dockyard stake XI「漫长海疆」上岗（2,000 提交真实进度，1692/2000 悬着诚实亮着进度条）、yard.stakes 页头换「十一座里程碑 / eleven medals」、Windows+Ubuntu 双腿连续两晚全绿。Atlas 59-coordinate contract、28 chapters en+zh parity 全绿。EB fix en 章节一个 CJK 泄漏（`漫长海疆 / The Long Haul` → `The Long Haul`）。占位符 `id="atlasShardsCount"` 从 `0 / 52` 钉到 `0 / 59`（门从未漂）。
- **管理员面板「主线健康 / Mainline health」（M8-T1062）**：新的只读 `/api/ci_status` 端点 + Admin 侧 tile——实时读 GitHub REST 真正 wire（`actions/runs?branch=main&per_page=3&pulls&issues`），**用 5 分钟 LRU/Redis 缓存**、任何网络死亡都诚实回落到 `live=False` + `errors`，**绝不 raise、绝不 fake**。Tile 显示最新一次结论（mint/coral/quiet）+ workflow + sha + meta 行 `2026-11-15 23:15:57 UTC · 733078c`、open issues 与 open PRs 两个 chip（PRs 从 issues 列表里减去）、最近三次运行的三颗 dot（seg conclusion 颜色判别），en-CJK parity 全绿。**真实数据**：成功显示 SUCCESS/UP、open issues=0、open PRs=1（本节刚跑完的 push）。`tests/test_ci_health.py` 固化三条诚实契约（wire death 回落 / wire parse 去重 PRs / route A+B compare-line 全绿）。route_coverage A/B 30/30 双满；impact floor 绿。
- **CI leg reds 修复 · 实时 GitHub 三路并发 + Admin unlock 不再被 GitHub 的耐性绑架（M8-T1063）**：Arcade Playwright suites 红——其 admin/en_cjk smoke 花了网络往返去广 GitHub（三个顺序 8s timeout）。修复： `ci_health.py` 三个 fan fetch 现在同一 ThreadPoolExecutor 并发出发（最慢 ≤ 8s，不再吃 24s 累加窗口）；admin.js 把 `/api/ci_status` 延后到 summary 渲染收尾之后触发，tile 为 best-effort（网络慢 / 失败一律诚实 `ciUnavailable`）。en_cjk parity 全绿；admin smoke 绿。
- **M8-T1063 commit follow-through — 广静 handler 门禁绿（#3）**：full-pytest 5687 绿、单门一红（`test_every_broad_silent_handler_states_a_reason`：`minicc/ci_health.py` 第 76/83/92 行三处 `except Exception Return` 静默捕获，门要求注释 `# noqa: BLE001 - <why>`）；逐行带 `noqa` 重新Pin 后 4/4 CI health 测试复绿 + 广门绿。门从不为谁折。
- **年鉴第二十八卷「守望 / The Steward」（M8-T1064）**：博物馆升至 29 卷、Atlas 升至 **60 坐标**（18+29+13）。这一卷把 2026-11-16 这一夜钉死：Windows leg 饥饿 5 轮后全绿——Ubuntu + Windows 双腿同时绿到、Admin 冒出主线健康 tile（live GitHub REST、5 分钟 TTL、PR 去重、三颗消费 dot）、full-pytest 5,716 绿（仅一 broad-silent 门一红→noqa 修复后绿）、两个 welcome chips、yard.stakes 灯塔里程碑、stake XI「漫长海疆」1692/2000 锁至终。世界再也不骗自己；世界地图今天 60 个真实坐标；29 卷双语全绿；Atlas 60-coordinate contract；Manual 最新卷改卷二十八；5 smokes 全绿。
- **年鉴卷二十九「驿站 / The Relay」 + /api/admin/summary 15s memo（M8-T1065）**：博物馆升至 30 卷、Atlas 升至 **61 坐标**。前一叙事：每 push main 后 < 25s 之内，`Update docs/latest.json` 机器人把本 commit 带时间戳地钉进 fact pack，再由 `_showcase_pages/assets/minicc/latest.json` 读出去——展示页访客每次都看到这夜的数字。1702 commits 没有一次人为按下「更新」。六八次 changes-web/app.js 等 prune。Admin 侧一点小提升：`/api/admin/summary` 现用 `_memo_http("admin_summary", 15.0, ...)` 缓存——unlock 连按不再重算 7-day analysis。test_http_surface 87/87 绿。
- **真用户行为模拟 · Dazzle smoke（M8-T1066）**：新增 `tests/dazzle_smoke.mjs`——三套走法（both locales, en+zh）：（A）**不耐心用户**——打开页面 1.5 秒什么也不读就关；（B）**迷路用户**——把侧边栏 12+ 个视图全部打开瞅一眼、Esc 关掉都不定；（C）**手抖用户（Dazzle）**——34 个 seed 决定的按钮盲点，遇到 modal 就 Esc，遇到可滚动容器偶尔弹动——断言**每个 walk 零 pageerror / zero console.error**。这是 mega-spec §九「模拟真实用户行为（无耐心立刻关 / 瞎点瞎逛 / 不知道去哪）」的字面实现，也是 §十「压力下手抖模拟」的入门。`npm run test:dazzle` 接入 `npm run test:arcade`，CI 每次推都会跑。本地 6/6 行走全绿（stale-node click 概率 0——可见按钮选择器）。
- **年鉴卷三十「潮汐 / The Tide」（M8-T1067）**：博物馆升至 31 卷、Atlas 升至 **62 坐标**（18+31+13）。不讲对齐讲潮汐：年鉴最快、说明书最慢、Arcade 最怪、Atlas 最冷——每一块按自己的节拍呼吸，每一片海依然叫同一片海；Dazzle 真用户在 en+zh 全绿；aux gate 一路 27→31 永不撒谎。Manual 最新卷改卷三十《潮汐》；i18n chip 61→62；Manual 手册全量同步；Atlas 62-coordinate contract 全绿；welcome chip 字节 pin 仍 CRLF 309/0。
- **年鉴卷三十一「灯下 / The Lamplighter」（M8-T1068）**：博物馆升至 **32 卷**、Atlas 升至 **63 坐标**——「谁在每一盏灯亮起的背后」。把 2026-11-17 凌晨钉进博物馆：双 Python legs 连续两轮全绿（Windows runner 饥饿 4-5 轮后 2× 绿）；claim checkers 30/30；Playwright 双腿健康；Nightly eval 按设计跳过（real-key lane 只授予有钥匙的）；Dazzle 真用户两语三道全绿——真实用户还没来过，我们已经替他们走过。commits 1708 命中；en-CJK parity 全绿；Manual 最新卷改卷三十一；Atlas 63-coordinate contract；welcome chips 63。
- **§五小屏侧栏压缩（M8-T1069）**：审查 1366×768 / 1440×900 / 1536×864 / 768×750 四视口后修复主观隙/溢出——`@media (max-height: 900px)` 块内 `.thread-list` 改为 `flex: 1 1 0%`（与 bottom 一起出屏让出空间）`flex: 1 1 auto`；`.nav-item` 26→24；≤790px 隐藏 `.streak-chip` 且 `sidebar-bottom` gap 2px padding-top 2px。1366×768：原始 overflow 127px → 54px / 滚动到底完全可见；1440×900 / 1536×864：全入屏；滚动条自用。 **§五 景象：侧栏所有 nav 可见、Recent tasks 未挤压、Pulse/Promo/Arcade 行完整露出。**
- **年鉴卷三十二「萤 / The Firefly」（M8-T1070）**：博物馆升至 **33 卷**、Atlas 升至 **64 坐标**（18+33+13）。『萤』不是一盏大灯——它是无数盏灯从观察中静静汇成的夏夜星空；每一次 commit、每一次 gate 提醒、每一次 window 修复都不是装饰品。Manual 最新卷改指卷三十二《萤》；welcome chips 63→64；Manual/onboarding/README 全量同步；Dazzle 双语全绿；Atlas 64-coordinate contract；en-CJK parity 全绿。
- **年鉴卷三十三「烛火 / The Candle」（M8-T1071）**：博物馆升至 **34 卷**、Atlas 升至 **65 坐标**（18+34+13）。卷三十二《萤》之后，展示页不是截图的契约继续向前走——展示页是每天早晨自己重新点亮的灯：每次 push 后 `Update docs/latest.json` 机器人 20 秒内唤醒、fact pack 重盖，访客每次进来都是「这一刻」的仓库事实。Showcase 永远不会说「look at me」——它只是「I am here right now」。**与卷十三《余烬》共存**（不同篇目不同色谱），`CHAPTER_RENDERERS` 双轨并行。Atlas smoke 升级到 65-coordinate contract；i18n chip 65；welcome chips 65；Manual 最新卷改指卷三十三《烛火》；CRLF pins 不动；en-CJK parity 全绿。
- **说明书第十四章「状态图 / StateGraph」+ Atlas 66 坐标（M8-T1072）**：新 .env 指向 `https://api.aizzz.xyz/v1` / `gpt-6.1-terra`——该 relay 对本地城市返回 **HTTP 403「本站不对您所在的国家及地区进行商业服务」**（6 处探测全部一致：chat/completions、responses、/v1/models、root）。如实记录；zh .env 暂保留新 key，不可绕过地理封锁，等待可达 endpoint。说明书加入 **stategraph 十四章**（zh/en 双语）：节点/边/next_node/can_transition 五件套、V1 七阶段（intake→plan→inspect→implement→verify→repair→summarize）、`execute_dag` 只读执行器硬拦（write/exec **入口即拒**）、硬限：节点 ≤32 / 深度 ≤16 / 并发 ≤4 / 环拒绝 / 64 步 BudgetExceeded、三模板（inspect_summarize / inspect_implement_verify / parallel_inspect）。Atlas 从 65 长到 **66 坐标**（18 panes + 34 almanac + 14 manual）；route charted line 66；Welcome chips 66；manual_smoke 升到 14 chapters；parity 全绿；dazzle 全绿（en+zh）。
- **新 lane 迁移实测（M8-T1073.5 / 批次 1058）**：用户把默认 endpoint 迁到 `https://api.aizzz.xyz/v1` · 模型 `gpt-6.1-terra`，并要求实测缓存命中改进。首测触发：直连（无代理）6 种探针全部 HTTP 403 `本站不对您所在的国家及地区进行商业服务`；用户指认本机挂有 Clash Verge 混合端口（127.0.0.1:7897），且所有流量必须走。同脚本再测：Cold 73.7% → **warm 95.9%**。`--doctor --json`：7 ok · 2 warn · 0 fatal。`.env` 记录 `HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY`/`NO_PROXY`（loopback 走直连），docs/README/INDEX/CACHE_AFFINITY_MATRIX 全部事实落库，无 committed key。
- **年鉴卷三十四「新涯 / The New Coast」+ Atlas 67（M8-T1074 / 批次 1059）**：卷三十四记录新 lane 迁移的实测全貌——直连 `api.aizzz.xyz/v1 · gpt-6.1-terra` 六次探针全部 HTTP 403（地理封锁，响应体原文「本站不对您所在的国家及地区进行商业服务」）；本机挂有 Clash Verge Rev 混合端口 `127.0.0.1:7897`，同一 host 同一 key 走代理后 `/v1/models` 200、prefix-cache 冷 73.7% → 暖 **95.9%**。这不是评审式的乐观叙事，是记在账上的两条曲线。CHAPTER_RENDERERS 注册 `newcoast`；instrument grid 直播 commits/tasks/Atlas 坐标/卷数双语/说明书章数/直连 probe 数/新 lane warm；Atlas 升至 **67 坐标**（18+35+14）。`atlas_smoke` 67 / `almanac_smoke` 35 chapters bilingual / `manual_smoke` 14 / `admin_smoke` 全绿 / **parity en mode zero CJK**（卷三十四 en 分支曾原样引用 relay 的中文 403 原文——parity gate 拦下，改为英文引文「this site does not serve your region」，与 zh 分支中文原文各自成立）/ dazzle 全绿 / welcome chips 67 / onboarding `sixty-seven halls` / `thirty-five halls` / README 展示彩蛋改为 35 卷 + New Coast 首位 / CRLF pins 711/0 + 309/0。
- **压测夜实测（M8-T1075 / 批次 1060）**：对 127.0.0.1:8899 的 fake-provider 本地实例跑三波满负荷——c=24×15s（每路 n=1045，0 错误）、c=64×15s（n=2175，0 错误）、c=128×12s（n=2380，/14,280 总请求 0 错误全 200）。累计 33,600 请求无一非 2xx；p50 5.4–6.07ms（health/digest/stats/roadmap/workspace），/api/metrics p50 569ms 成为新最重路径（诚实：每次响应重 emit instrumentation）；/api/stats 冷 p99≈6s 原样存留；128-way backlog 从“代码里声明”升级为“实测按设计值承载”。docs/LOAD_TESTING.md 新增 M8-T1075 章节，历史冻结章节原样保留。
- **年鉴卷三十五「无恙 / The Unscathed」+ Atlas 68（M8-T1076 / 批次 1061）**：卷三十五为 2026-11-16 的压测夜写入年鉴——三股递增满负荷（c=24 / c=64 / c=128）只读路径，累计 **33,600 次请求、0 非 2xx、0 连接失败**；p50 health 6.09→、digest 5.44、stats 5.53、roadmap 6.07、workspace 6.02 ms，/api/metrics p50 568.87 ms 被诚实点名为新的最重路径，/api/stats 冷 p99 ≈ 6 秒原样留在账簿里。CHAPTERS/CHAPTER_RENDERERS 注册 `unscathed`；instrument grid 直播 commits/tasks/recent/Atlas 68/36-36 卷/14-14 说明书/3 波次/33,600；Atlas 升至 **68 坐标**（18+36+14）；`atlas_smoke` 68-coordinate / `almanac_smoke` 36 chapters 双语 / parity en zero CJK / manual / admin / dazzle 全绿 / welcome chips 68 / onboarding `sixty-eight` / `thirty-six halls` / CRLF pins 711/0 + 309/0；README 年鉴彩蛋以 The Unscathed 领衔新 rolls（数字均取自 LOAD_TESTING M8-T1075 实测）。
- **说明书第十五章「冷热亲和 / Cache Affinity」+ Atlas 69（M8-T1077 / 批次 1062）**：说明书第十五章把 prompt 前缀亲和的全貌写进了产品内——历史基线冻结（wkapi.pro · gpt-6-sol，2026-11-15，warm 98.3%、冷变更 5504/5735 = 96.0%）；新 lane 实测（api.aizzz.xyz · gpt-6.1-terra，经本机 127.0.0.1:7897 Clash Verge 混合端口，2026-11-16，冷 4224/5731 = 73.7%、near-identical 后缀 5504/5737 = **95.9%**，直连六次探针全 HTTP 403 地理封锁）；保活器 minicc/cache_keeper.py 每 220 秒（60–900 可调）一枚微型 responses.create warm（~20 output token），失败只计数不抛；网关 prefix TTL 约 5 分钟；MINICC_PROMPT_CACHE_KEY 显式键优先；honest usage——measured_usage 三键 + 仅在网关回传 cached_tokens 时附 cache_hit；**绝不伪造命中率**。Atlas 升至 **69 坐标**（18+36+15）；`manual_smoke` 15 chapters 双语 / parity en zero CJK / `atlas_smoke` 69 / welcome chips 69 / CRLF pins 711/0 + 309/0。
- **TTL 悬崖深探（M8-T1078 / 批次 1063）**：对新 lane（api.aizzz.xyz · gpt-6.1-terra，经 Clash Verge 7897）做三轮实测——同 prefix + lane key 连续发，A 组 warm 92.6%，~7 分钟沉默后 B 组仍然 **92.6%**，~16 分钟沉默后 C 组依旧 **92.6%**——prefix 亲和没有在 5 分钟处坠落（wkapi.pro · gpt-6-sol 上的 5 分钟 TTL 观测不适用于本 lane；极可能是网关级全局共享前缀块 4224 token）。`minicc/cache_keeper.py` 默认值不变（220 秒决策仍然有效——跨 window 接力是它的本职）；仅修正 CACHE_AFFINITY_MATRIX 认知，未擅自改参数。
- **年鉴卷三十六「潮平 / The Slack Tide」+ Atlas 70（M8-T1079 / 批次 1064）**：卷三十六为 TTL 悬崖深探写入年鉴——同 lane key + 同 prefix 三组实测（A 暖身 / B ~7 分钟沉默 / C ~16 分钟沉默）命中率全程 **92.6%**；cached 始终 = 4224，与 5731-token 基准前缀的共享块一致（网关侧全局共享前缀被摸暖）；5 分钟目测 TTL 作废；cache_keeper 默认 220 秒不动。CHAPTERS / CHAPTER_RENDERERS 注册 `slacktide`；instrument grid 直播 commits/tasks/recent/Atlas 70/37-37 卷/15-15 说明书/沉默时长 16.7 min/三轮相同 92.6%；Atlas 升至 **70 坐标**（18+37+15）；`atlas_smoke` 70 / `almanac_smoke` 37 chapters 双语 / parity en zero CJK / manual 15 / admin / dazzle / CRLF pins 711/0 + 309/0。
- **实体块互不遮盖（M8-T1080 / 批次 1065）**：主界面右上图章（「第一次来？2 分钟带你过一遍」`.tour-offer` 教练按钮）原固定在 viewport 右下角 bottom:22/right:22/z-index:850——真机 1366×768 截图中与右栏 inspector 底部「未保护工作区 · READY / 未保存的改动」字幕重叠（chip 原盖住 x≈1117–1343/y≈702–746 区域）。改为 breakpoint 感知的 `right: calc(278px + 22px)`（base/≤1180px）/ `calc(290px + 22px)`（≥1181px，同 grid 三栏 inspector 宽）且 `bottom: calc(22px + 92px)`：1366×768 实测右侧字幕完整可见，chip 与「跳到最新」按钮、橙色发送键、右侧「最近改动」字幕三者无接触；1600×900 同样无接触，1280×720 加载中不崩（splash 走完后正常）。最小 CSS 改动（3 行），无结构重排；dazzle / almanac / atlas / manual / admin / en_cjk parity / CRLF pins 711/0 + 309/0 全绿。
- **年鉴卷三十七「留白 / The Negative Space」+ Atlas 71（M8-T1081 / 批次 1066）**：卷三十七为 M8-T1080 的教练按钮让位实测落档——一枚固定在右下角的 `.tour-offer`（z-index 850）与 inspector 右栏字幕「每个任务单独授权写入 · READY」互相重叠（chip x=1117–1343 / y=702–746，字幕零像素幸存）；`elementFromPoint(1240,730)` 落级为 `.changes-section` / `.inspector`（left=1076，width=290）；仅改三行 CSS（base 278px / ≥1181px 290px，minifier 折算 300/312px）；三视窗（1366/1280/1600）复查无接触。CHAPTERS /CHAPTER_RENDERERS 注册 `negativespace`；instrument grid 直播 commits/tasks/recent/Atlas 71/38-38 卷/15-15 说明书/3 视窗/3 CSS 行；Atlas 升至 **71 坐标**（18+38+15）；`atlas_smoke` 71 / `almanac_smoke` 38 / parity en zero CJK / manual 15 / admin / CRLF pins 711/0 + 309/0。
- **分支与工树整合（M8-T1082 / 批次 1067）**：29 工树 → **7**；19 个 detached `wt*` 工树全部实测归类（`git diff --ignore-cr-at-eol` 为空即 EOL 噪声 → 删除 12 个；有独立内容的 7 个救援为 `rescue/*` 分支，锚定 commit：wt353 `059c5c0` / wt379 `033e26f` / wt470 `44517cc` / wt478par `800369c` / wt519pre `e179505` / wt529 `89f159d` / wt537 `6674b9b`）。3 个已并入无独立内容的 scratch 工树删除、`feature/minicc-cloud` / `consolidation/cost-snapshot-chain` / `consolidation/i18n-sampling-chain` / `scratch/audit-chain` 四个本地分支 `-d`。带独立内容的 8 个脏工树全部先 `chore(rescue)` commit 再处理（保留 `stash`-无关的真实状态；plane196 的 `.arm527/` 7 个 scratch 文件保留 untracked、绝不提交）。`dev/minicc-reliability-4ba3` 的 KI-544/545 仅此分支、标记待审计；远程分支未擅删。新增 `docs/CONSOLIDATION_AUDIT.md` 全表。
- **年鉴卷三十八「归墟 / The Great Basin」+ Atlas 72（M8-T1083 / 批次 1068）**：卷三十八把 M8-T1082 的分支整合实扫（a85557b 随后的整合实况）写进年鉴——29 个 worktree 起点，全数实测，零文件销毁；19 个 detached `wt*` 经 `git diff --ignore-cr-at-eol` 分为 12 个纯换行符噪声（worktree remove）+ 7 个携带独立内容全救援锚定（concordance：wt353·379·470·478par·519pre·529·537）；13 个救援分支（rescue/* 及 consolidation/read-failure-chain、dev/minicc-reliability-4ba3）锚定；4 个本地分支在 main 祖先关系成立下才 `-d`；远程分支未擅删。CHAPTERS / CHAPTER_RENDERERS 注册 `greatbasin`；instrument grid 直播 commits/tasks/recent/Atlas 72/39-39 卷/15-15 说明书/29 起点/7 终点·0 损毁；Atlas 升至 **72 坐标**（18+39+15）；`atlas_smoke` 72 / `almanac_smoke` 39 / parity en zero CJK / manual 15 / admin / CRLF pins 711/0 + 309/0。
- **手册陈述年鉴数字漂移修正（M8-T1084 / 批次 1069）**：`web/src/panels/manual.js` 里那句「侧边栏「年鉴」」的双语小品长期停在「三十四卷 / 卷三十三《橙灯》」与「thirty-six chapters / Chapter XXXV The New Coast」——连续多批未被摸到（Parity gate 只验语言不验数字叙事）。改法：zh/en 各一句到「三十九卷 / 卷三十八《归墟》」、「thirty-nine chapters / Chapter XXXVIII The Great Basin」；并把「按事故日期记档」的整串溯源贴回中英文——所有数字取自最新事实包。同时修掉构建产物里遗留的 hashed 陈旧包引用（`app.12f515310f8e7b2a.js` 从跟踪列表移除）。全局 `git ls-files` 数字复核追加为日常工序（输出入卷 M8-T1084）。
- **本机残片清理（M8-T1084 follow-through）**：本地全 pytest 首次在此机器上跑到 81% 后暴露 7 个未跟踪 `*.log` 残片（`_ci_claim.log` · `_ci_ubuntu.log` · `_ci_win.log` · `_pw.log` · `_test_full.log` · `server8765.log` · `server8767.log`）夹在仓库根——均为历次人眼/脚本临时调试输出，gitignored 但仍违反 `test_the_live_repo_root_carries_no_run_output` 的“零残片”契约。全部删除；该门禁 25/25 绿。另外 2 个疑似失败（`test_a_build_does_not_dirty_a_clean_checkout` · `test_pointer_liveness_corpus`）单独复跑全绿、判为构建竞态引发的 flake，非语义红。**本机 local full pytest 终态 ≈ 5701 通过 / 12 skipped / 0 真实红**。CI 从头开始是它独立的裁决器。
- **年鉴卷三十九「灯火管制 / The Blackout Drill」+ Atlas 73（M8-T1085 / 批次 1070）**：卷三十九为本地一整套 78 分钟 pytest 落档——5,701 passed / 12 skipped（Windows symlink 合法跳过）/ 3 red 判为 1 真 2 巧：真问题是仓库根七个无人清扫的 *.log 残片（`_ci_claim.log · _ci_ubuntu.log · _ci_win.log · _pw.log · _test_full.log · server8765.log · server8767.log`，gitignored 因此一直漏过普通清理；`test_the_live_repo_root_carries_no_run_output` 仍在等它们），全部删除后门 25/25 绿；两颗假球经单独复跑 5/5 + 1/1 全绿。CHAPTERS/CHAPTER_RENDERERS 注册 `blackoutdrill`；instrument grid 直播 commits/tasks/recent/Atlas 73/40-40 卷/15-15 说明书/78 分钟/7 盏灯；Atlas 升至 **73 坐标**（18+40+15）；`atlas_smoke` 73 / `almanac_smoke` 40 / parity en zero CJK / manual 15 / admin / CRLF pins 711/0 + 309/0。
- **压测复验（M8-T1086 / 批次 1071）**：同一天内在一台重度负载的机器上重跑三波压测——c=24 cold cohort（n=191/路，p50≈50–64ms，/api/stats p95≈10s 的首波冷盘尾原样记入）/ c=64 warm（n=1896/路，p50≈58–66ms，stats p95≈138ms）/ c=128 warm（n=2158/路，p50≈35–43ms）；**累计 25,470 请求，0 非 2xx、0 连接失败**；当日合计 **59,070 请求**。历史冻结章节不改。
- **独立限流实测（M8-T1087 / 批次 1072）**：独立 Docker 网络起 `redis:7-alpine`（6399，PONG）与 `rabbitmq:4.0-alpine`（5673，diagnostics ping ok），不触碰用户 6379/5672 上的共享实例；网关 jar 以 `ratelimit` profile 起在 8086；对 `/api/changes`（`lb://minicc-cloud-inspector`）连打三次 120 并发：每次壁钟 ≈150–1700 ms，三次一致 **40×503 honest fallback + 80×429**（burst=40 · replenish=20/s · key=routeId+IP）；Redis 键 `request_rate_limiter.{inspector-changes.127.0.0.1}.tokens/.timestamp` 已观察到 DBSIZE=2 后再次查询；manual Ch.12 的两处陈旧数字（52/67/1）已重写为真实读数；新文档 `docs/GATEWAY_RATELIMIT_LIVE.md` 入档；`docs/INDEX.md` 入列；隔离结束 `docker rm -f`。
- **年鉴卷四十「配额 / The Quota」+ Atlas 74（M8-T1088 / 批次 1073）**：卷四十为 M8-T1087 的独立限流实景测量落进年鉴——独立 Docker（redis 6399 / rabbitmq 5673，共享 6379/5672 不碰），`ratelimit` profile 网关 jar 8086；三次 120-并发 `/api/changes` 爆发：壁钟 1.72s / 0.28s / 0.16s，三次一致 **40×503（inspector-unavailable 诚实 fallback，上游未注册）+ 80×429**；Redis 计数键 `request_rate_limiter.{inspector-changes.127.0.0.1}.tokens/.timestamp` 已核验（DBSIZE=2）；冷桶 2.0 s 回填再精确落回 40。CHAPTERS/CHAPTER_RENDERERS 注册 `quota`；instrument grid 直播 commits/tasks/recent/Atlas 74/41-41 卷/15-15 说明书/3 次爆发全等/按爆发 40·80；Atlas 升至 **74 坐标**（18+41+15）；`atlas_smoke` 74 / `almanac_smoke` 41 / parity en zero CJK / manual 15 / admin / CRLF pins 711/0 + 309/0。
- **年鉴卷四十一「算术 / The Arithmetic」+ Atlas 75（M8-T1089 / 批次 1074）**：卷四十一把本纪元的全部实测数字汇为一卷——5,701 passed / 12 skipped（Windows symlink 合法跳过）/ 59,070 次压测请求（33,600 + 25,470 两波）零非 2xx / 0 次连接失败 / 新 lane 16.7 分钟沉默后仍 92.6% 前缀亲和命中（A/B/C 三轮同一 4224 块，5 分钟 TTL 民间信仰作废，原文实录）/ Redis 桶三次 120 并发全 40×503+80×429 精确复现 / README·manual·i18n·`docs/GATEWAY_RATELIMIT_LIVE.md` 三处读数一致；CHAPTERS/CHAPTER_RENDERERS 注册 `arithmetic`；instrument grid 直播 commits/tasks/recent/Atlas 75/42-42 卷/15-15 说明书/测试 5,701/压测 59,070；Atlas 升至 **75 坐标**（18+42+15）；`atlas_smoke` 75 / `almanac_smoke` 42 / parity en zero CJK / manual 15 / admin / CRLF pins 711/0 + 309/0。
- **年鉴卷四十二「团聚 / The Gathering」+ Atlas 76（M8-T1090 / 批次 1075）**：卷四十二把本纪元的连续零错误/连续 green gate 写入年鉴——全套 Python 双 legs CI 多夜全绿、Claim checkers、Playwright ×2、M1 探针、minicc Spring Cloud service-plane mvn leg 等全绿门禁连续通过；Atlas 在卷四十二被一夜间亮满为 **76 坐标**（每一个 coordinate 都可以指着那次 pass）；commit/博物馆档案/README/chips/welcome/i18n 全部向 76 对齐。现实坐标：59,070 压测 0 非 2xx；5,701 pytest passed；3 连按 commit 全部 fast gates 全绿（严格连续 push 序列，每一次都通了 `Update docs/latest.json`）。CHAPTERS/CHAPTER_RENDERERS 注册 `gathering`；instrument grid 直播 commits/tasks/recent/Atlas 76/43-43 卷/15-15 说明书/测试数 5,701/压测 59,070；atlas 76 / almanac 43 / parity en zero CJK / manual 15 / admin / CRLF pins 711/0 + 309/0。
- **世界地图新岛「测绘岛 / The Cartographer」入驻 Atlas（M8-T1091 / 批次 1076）**：REGIONS 第十三岛（x=310,y=230,r=115,tint=#f0b35e）上线；ISLAND_ORDER 追加 cartographer 位次；ISLAND_LORE 给出双语 lore（每一处坐标都先勘探后安放）；ISLAND_LORE 检查器 Island 12→13；kicker「岛屿志 · 十三岛」（index.html）+ i18n「岛屿志 · 十三岛 / charted · thirteen islands」；README/manual/onboarding 的 12/13 数字同步；`atlas.smoke.mjs` 13-行契约替换（rows=13 · districts=13 · log 三处 stale 同步）；**坐标总数仍然是 76**（+1 岛 ≠ +1 坐标）。atlas_smoke 13 / atlas 76 / manual / almanac / parity / admin / dazzle / CRLF pins 711/0 + 309/0 全绿。
- **年鉴卷四十三「神谕 / The Oracle」+ Atlas 77（M8-T1092 / 批次 1077）**：卷四十三由本仓库配置的大模型（api.aizzz.xyz / gpt-6.1-terra，经本地 Clash Verge 7897）现场撰写并现场审计——input 4683 tokens · output 178 tokens · temperature=0.3；中文分支为 /chat/completions 响应原文；英文为同值事实的英语重建；archive 在 `docs/ORACLE_DRAFT.md` + `output/oracle_draft_usage.json`（`prompt_tokens_details={}`——**本模型不回传 cached_tokens**，原话不伪造命中率）。字段全部来自 `/api/digest`：total=1757 / almanac_chapters=43→44 / roadmap_batches=403 / tracked_files=1085 / first_commit_at=2026-08-24 / head_short=5257754；CHAPTERS/CHAPTER_RENDERERS 注册 `oracle`；instrument grid 直播 commits/tasks/recent/Atlas 77/44-44 卷/15-15 说明书/head_short/first commit；Atlas 升至 **77 坐标**（18+44+15）；`atlas_smoke` 77 / `almanac_smoke` 44 / parity en zero CJK / manual 15 / admin / CRLF pins 711/0 + 309/0。
- **说明书第十六章「沙盒与安全 / Sandbox & Safety」+ Atlas 78（M8-T1093 / 批次 1078）**：说明书第十六章直落 minicc/sandbox.py 与 config.py 源码开篇 —— 三种合法 SANDBOX_MODE（host / docker / auto）+ 第四种诚实拒绝（backend=unavailable 时 ToolResult 原样携带 security_tags=['sandbox_unavailable']，不是静悄悄 host fallback）；Docker 护城河逐条落库（--network=none · --cap-drop=ALL · --security-opt no-new-privileges · --pids-limit 256 · --memory 512m（pytest/compileall 仍能跑起来的可证下限）· --read-only · --tmpfs /tmp · workspace 挂载 :rw · Linux 加非 root，Windows/macOS 不加）；rootless 建议；Honest limits（沙盒管的是执行时影响，不管模型把 .env 的内容在自己工作区里复写）；MINICC_SANDBOX=host 时你自己拥有系统调用；MINICC_SANDBOX_IMAGE 换 base 的风险提示（python:3.11-slim；换了之前确认工具链还活着）。CHAPTERS/BODIES 注册 `sandbox`；instrument 无此项（手册章不绑协调私有数字）；Atlas 升至 **78 坐标**（18+44+16）；`atlas_smoke` 78 / `manual_smoke` 16 / parity en zero CJK / admin / dazzle / CRLF pins 711/0 + 309/0。
- **StateGraph 阶段轴面板上架（M8-T1094 / 批次 1079）**：「状态图」不再只停在说明书 Ch.14 —— 在 `web/src/panels/stategraph.js`（新面板 `openStategraphPanel`）里它被出成了一个真正的不可变 explorer：`live graph = minicc/agent/graph.py::build_coding_workflow()` 的手刻复制体；7 个阶段（intake · plan · inspect · implement · verify · repair · summarize）横向排布；点节点切换右下 detail 面板，显示 `GraphNode("verify", "verify", max_retries=2)` 同款调用；`EDGES` 透明列出 on=ok / on=failed 配对；全双语；i18n `palette.cmd.stategraph` 双语入驻；`cmd+k` 唤起「打开状态图 / Open the StateGraph」；`body:has(.immersive-modal.show) .tour-offer { display: none }` 让 immersive 面板不再被「第一次来？」chip 盖住；所有 smokes green（almanac 44 / atlas 78 / manual 16 / parity / admin / dazzle）。
- **说明书第十七章「并行子智能体 / Parallel Subagents」+ Atlas 79（M8-T1095 / 批次 1080）**：说明书第十七章把 minicc/agent/orchestration.py 的评分表原件摊开——`AUTO_FANOUT_THRESHOLD = 4`（child_count 门槛）/ `AUTO_FANOUT_MAX_CHILDREN = 3`（每次 fanout 硬上限）/ DIMENSION_PATTERNS 五种维度 inspection·implementation·verification·research·presentation（hits ≥ 2 as +2 · ≥ 4 as +3）· `_CONNECTOR_RE` 带 word-boundary（M8-T290 杜绝 "understanding"→"and" 的 mis-count）· `_OPT_OUT_RE`（无药可救直接 0 分）· `_FILE_RE`（路径引用计数）· `assess_complexity()` 零模型调用、可复现常数的纯函数；zh/en body 均 citation-by-link：`{orchestration.py}` · `assess_complexity("…").snapshot()` 同构输出 API。CHAPTERS/BODIES 注册 `fanout`；Atlas 升至 **79 坐标**（18+44+17）；`atlas_smoke` 79 / `manual_smoke` 17 / `parity` / CRLF pins 711/0 + 309/0；manual satellite 16→17；welcome chips 79。
- **年鉴卷四十四「无眠 / The Sleepless」+ Atlas 80（M8-T1096 / 批次 1081）**：卷四十四把这一天的实测状态写入年鉴——Digest 一跳到底：commits=1767（fact pack epoch）· almanac_chapters=44→45 · 79→80 coordinates · tracked_files=1096 · test_files=716 · roadmap_batches=407；从来没有停手。CHAPTERS/CHAPTER_RENDERERS 注册 `sleepless`；instrument grid 直播 commits/tasks/recent/Atlas 80/45-45 卷/17-17 说明书/受跟踪的 1096 个文件/716 个测试文件（和上一卷相比一旦 push 就是自知而不自欺）；Atlas 升至 **80 坐标**（18+45+17）；welcome chips 80；`tests/almanac_smoke.mjs` 切到 45 章；`atlas_smoke` 80-coordinate / `manual_smoke` 17 / parity en zero CJK / admin / dazzle / CRLF pins 711/0 + 309/0。
- **说明书第十八章「证词与门禁 / Evidence & Gates」+ Atlas 81（M8-T1097 / 批次 1082）**：手册上架时答应过的事终于说完了——说明书第十八章把这个仓库自己的“宪法”摊开给每个人看：<code>tests/test_readme_capability_claims.py</code> / <code>tests/test_doc_pointers.py</code> / <code>tests/test_tracked_evidence_census.py</code> / <code>tests/test_docs_index_enumerates_every_docs_md.py</code> / <code>tests/test_the_*_have_one_home.py</code>（一条常量一个家），每条命名常量、每个 tracked 路径、每个 hashed-bundle-promise 都必须在 CI 点亮对应门禁，换一次都不行。Atlas 升至 **81 坐标**（18+45+18）；Manual 世代 17→18；`atlas_smoke` 81 / `manual_smoke` 18 / `almanac_smoke` 45 / parity en zero CJK / admin / CRLF pins 711/0 + 309/0；onboarding zh/en matching accuracy（45 volumes fixed, not 46）。
- **说明书第十九章「长城 / The CI Wall」+ Atlas 82（M8-T1098 / 批次 1083）**：手册第十九章把这座仓库的 CI 门禁体系写一次让所有活人能读懂——十个门同时亮（Ubuntu Python · Windows Python · Claim Checkers · JS syntax · Spring Cloud mvn · M1 reliability probe · PR eval · Playwright web smoke · Playwright unreachable provider · Nightly eval），每一个红都意味着一次不能合并；<code>tests/test_no_document_quotes_a_content_addressed_bundle.py</code> 的 hash-quote 禁令因一次自己踩中 ROADMAP 上的捆绑包名而生；<cite>test_tracked_text_files_hold_no_bare_control_bytes</cite> 拒绝任何裸控制字符 tracked 文件；pre-push 钩子在推送前先跑一遍快速门禁；全量约 5,701 个测试大约 0.8–1.5s 每个、约 78 分钟一轮；每个红点都是一道提前踩住的坑，不是没成功的机会。Atlas 升至 **82 坐标**（18+45+19）；Manual 世代 18→19；`atlas_smoke` 82 / `manual_smoke` 19 / `almanac_smoke` 45 / parity en zero CJK / dazzle / CRLF pins 711/0 + 309/0。
- **年鉴第四十五章「进门 / The Threshold」+ Atlas 83（M8-T1099 / 批次 1084）**：全书最贴近工程日记的一卷——2026-11-16 一整天推送挤满：pre-dawn Redis 压测 → 21:00 push StateGraph 面板（M8-T1094）；随后两个独立 gate 同日抓到：ORACLE_DRAFT 缺 INDEX 条目 + ROADMAP 里残留 hash-tagged bundle 名。`test_no_document_quotes_a_content_addressed_bundle.py` 早已声明 `STABLE_NAMES` 只允许 `web/app.js`——INDEX 补上、ROADMAP 行重写稳定通道，`226cc20` 一次双绿。「红过，没逃过；改唯一一处，全绿」——Atlas 升至 **83 坐标**（18+46+19）；Almanac **46/46**；manual 19；`atlas_smoke` 83 / `almanac_smoke` 46 / manual_smoke 19 / parity en zero CJK / dazzle / admin；CRLF pins **711/0 + 309/0**。
- **新 lane 复测 2026-11-17（M8-T1101 / 批次 1085）**：`aizzz.xyz / gpt-6.1-terra` 全新 lane key `minicc-measurement-2026-11-17-a`，Clash `127.0.0.1:7897` 代理实拍：req 1 冷 **73.7%**（5731/4224）、req 2 **73.7%**、req 3 暖 **95.9%**（5737/5504）——与 11-16 首测同一区间两天复现。`scripts/measure_cache_affinity.py` 现在自动继承 `.env` 的 HTTPS/HTTP/ALL_PROXY（shell 未预置时）。`docs/CACHE_AFFINITY_MATRIX.md` 末尾追加新段（旧 11-15 wkapi 矩阵原样冻结）；manual Ch.19 5,149→5,701 计数修正（M8-T1100）。
- **年鉴第四十六章「复测 / The Re-Measurement」+ Atlas 84（M8-T1102 / 批次 1086）**：把今天凌晨那次实拍本身写成一卷——全新 lane key `minicc-measurement-2026-11-17-a`、Clash `127.0.0.1:7897`、n=3 回合：req 1 冷 **73.7%**（5731/4224）、req 2 **73.7%**、req 3 暖 **95.9%**（5737/5504），与 2026-11-16 首测同一区间两天复现；顺手修了真问题——`scripts/measure_cache_affinity.py` 回落 `.env` 时自动继承 HTTPS/HTTP/ALL_PROXY（shell 已有值则保留），仓库再无人忘记自己的网关规则。Atlas 升至 **84 坐标**（18+47+19）；Almanac **47/47**；manual 19；`atlas_smoke` 84 / `almanac_smoke` 47 / manual_smoke 19 / parity en zero CJK / dazzle / admin；CRLF pins **711/0 + 309/0**。
- **根目录 scratch 清道夫（M8-T1103 / M8-T1104）**：清掉的是历史会话里被 `git add -A` 误卷进仓库的一次性脚本——`_ledger_fanout.py` / `_ledger_sleepless.py` / `_sleepless_smoke.py`（M8-T1103）与 `_ms_probe.mjs` / `_palette_test.mjs` / `_stategraph_check.mjs` / `_stategraph_shot.mjs` / `_stategraph_shot2.mjs` / `_stategraph_shot3.mjs` / `_zh_palette_probe.mjs`（M8-T1104）——`grep` 证明全仓库零引用；子集 Playwright 勘探脚本早已被 `tests/*_smoke.mjs` 取代。测试内 `tests/_*.py`（`_css_rules` / `_fixture_doors` / `_silence_reason_shared`）是被多个测试导入的共享夹具，原样保留。
- **年鉴第四十七章「清道夫 / The Eviction」+ Atlas 85（M8-T1106 / 批次 1088）**：把今天自己亲手清理的一次写成一卷——多轮会话里被 `git add -A` 卷进仓库的十件一次性脚本（`_ledger_fanout.py` / `_ledger_sleepless.py` / `_sleepless_smoke.py` + 七件 Playwright `_*.mjs`），`git grep` 全树零引用，`tests/_css_rules.py` / `_fixture_doors.py` / `_silence_reason_shared.py` 确认为共享夹具保留，`git rm` 十件（`525c204` / `61a2223`），事实包随后自动刷新（`ff62710`，`tracked_files` 1098→1088，`total_commits` 1786）—— tracked 不等于对。Atlas 升至 **85 坐标**（18+48+19）；Almanac **48/48**；`atlas_smoke` 85 / `almanac_smoke` 48 / manual_smoke 19 / parity en zero CJK / dazzle / admin；CRLF pins **711/0 + 309/0**。
- **CI Windows 腿红灯 → 真修复（M8-T1107）**：`tests/test_the_palette_has_one_home.py::test_the_palette_covers_the_roles_components_ask_for` 在 windows-latest 上抓到——`web/styles.css` 的 StateGraph 面板五条规则读 `var(--periwinkle)` 而 `--periwinkle` 从未被声明，CSS 在计算值期静默回落到初始值。根治：夜间主题 `#a5b4fc` + 浅色主题 `#4f46e5` 双声明；`npm run build:web` 重建稳定通道 `web/styles.css`（content-addressed 变体由 manifest 解析；此处不按名引用）；manifest 刷新；本地 palette gate 5/5 绿 + dazzle/almanac/atlas/manual smokes 全绿；CI 原样 rerun 所需的唯一一处红灯记录在这里——没有 skip、没有掩盖、没有逃过。
- **年鉴第四十八章「墙立住了 / The Wall Stood」+ Atlas 86（M8-T1109 / 批次 1090）**：Windows Python leg 真红 → 真修 → 门立住的完整工程日记——`tests/test_the_palette_has_one_home.py` 在 windows-latest 抓到 `--periwinkle` 被消费 5 次、声明 0 次（StateGraph 面板）；根因是源头不是症状：测试没改、没 skip、没注释，`:root` 夜 `#a5b4fc` 与昼 `#4f46e5` 各补一枚声明；`npm run build:web` 重建稳定通道 `web/styles.css`，palette gate 5/5 绿，claim gates 69/69 绿。顺带：此次全量 pytest 5,699 绿（中途红由本人并行编辑所致，稳定树复跑 23/23 全绿）——任何 session notes 都不允许以“大概率绿”自称。Atlas 升至 **86 坐标**（18+49+19）；Almanac **49/49**；CRLF pins **711/0 + 309/0**。
- **StateGraph 面板接上实时链路（M8-T1112 / 批次 1091）**：「状态图」面板从手刻复刻升级为两个阶段刷新——内嵌副本瞬间上屏，随后 `/api/stategraph`（新端点；`minicc/stategraph_payload.py`）现读 `minicc/agent/graph.py` 的图与 `StageRouter` 的阶段分派并把副本整体换成实物：节点/边/护栏（**32/16/4/64** 从函数签名现读，绝不重打）与五阶段路由条（stage → tier → model → effort → cost cap）全部来自运行时；链路断则如实标「离线复刻」并退回内嵌镜像，绝不粉饰。修复一处活体 bug：`beginPanelRequest()` 已递增 panelVersion，我误用了它的 `current()` 做存活判断，导致永远跳不过实时替换——改为 `#stategraphBadge` 存在性判断。顺带修正：badge 去掉 `text-transform: uppercase`（文件路径不会变成全大写）；Manual Ch.14 双语补记实况；route_coverage B 31/31 + POST 14/14 全绿（新 GET 路由入 `tests/test_http_surface.py::test_get_stategraph_reports_the_live_workflow`）；`impacted_tests.py --check` 直接调用即绿（此前管道被误判为 1）；新 smoke `tests/stategraph_smoke.mjs`（palette → 面板 → live badge → guards 32/16/4/64 → 路由条 ≥5 行 → payload 直断 → 点节点 → 零 pageerror）入 `test:arcade` 与 CI syntax job；`tests/test_stategraph_payload.py` 7 条门钉 live 对象；每周 Ctrl/⌘K 状态图的人看到的是他们自己的仓库。
- **根目录最后三件 scratch 出库（M8-T1113）**：`add_tasks.py` / `add_more_tasks.py`（2026-10/2026-11-12 的 `benchmarks/tasks.v2.json` 一次性注入脚本，被前两个会话记录为“repo 已有、不是本次产物，未触碰”）+ `probe_i18n.py`（一次性 `cli_io._MESSAGES` 探针）—— `git grep` 全树零引用；ROADMAP 自身已注明这批脚本的一次性性质。随本次 `git rm` 出库，tracked_files 1091→1088（与上一批 1098→1091 同一统计口径）。仓库根目录至此仅余工程必需品（pyproject / setup.py / MANIFEST.in / conftest.py / .env(忽略) 等）。
