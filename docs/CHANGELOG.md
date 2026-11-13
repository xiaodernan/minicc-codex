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
