# minicc 文档索引

本仓库的文档不是孤岛。读者从任何一篇入口都应至少能走到其他一篇；这份索引是那扇门。

## 开箱

- [FIRST_HOUR.md](FIRST_HOUR.md) —— 装到第一次成功。按 `--setup` → `--doctor` → `--stats` → `--capabilities` → `--version` → 首次进模型的顺序展开，每步实测。
- [CHANGELOG.md](CHANGELOG.md) —— 2026-09-20 至今合流记录；M1..M8 的落成面、已知边界（CI-only packaging 门、nightly 跳过）。
- [ROADMAP_TO_PRODUCT.md](ROADMAP_TO_PRODUCT.md) —— 合流批次账本（批次 601→748）：每批欠的哪一条、改动、验证、边界，`git log` 之外的叙事证据。
- [CONTRIBUTING.md](CONTRIBUTING.md) —— 贡献者流程：环境准备、三道必跑门、批次账本格式、One Fact One Home 方法。

## 运行与自检

- [OPERATIONS.md](OPERATIONS.md) —— 运维和自检手册：`--setup`、`--doctor`、`--doctor-strict`、`--stats`、`--version --json` 的语义与退出码契约，网络访问前提，状态目录规则，`--json` 各 flavor 的键形状。
- [CLI_REFERENCE.md](CLI_REFERENCE.md) —— 全部命令行旗标按分类（连接/安全/上下文/会话/自检）列出，以 `--help` 实际输出为准。
- [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) —— 评测面：任务套件结构、grading_coverage 的两个自报口径、nightly 绝对门的环境变量。

## 在线接口与服务面

- [SERVICE_PLANE_PLAN.md](SERVICE_PLANE_PLAN.md) —— 服务面规划（P1..P5），registry / config / inspector / tasks 五模块的角色与边界。
- [SERVICE_PLANE_OPERATOR.md](SERVICE_PLANE_OPERATOR.md) —— 服务面运维：standalone 启 tasks、SQLite 只读、curl 实录（含 999-limit 被钳后的 `X-Minicc-Tasks-Limit: 100`）、Compose。
- [SERVICE_PLANE_GATEWAY.md](SERVICE_PLANE_GATEWAY.md) —— 网关路由与 Resilience4j 配置的事实档（路由行、breaker 参数、暴露的 actuator 端点）。
- [AGENT_LLM_ROADMAP.md](AGENT_LLM_ROADMAP.md) —— 引擎与模型的长期路线（Provider / tool 模式）。
- [AGENT_RESEARCH.md](AGENT_RESEARCH.md) —— 外部调研与参考来源。
- [REFERENCE_ARCHITECTURE.md](REFERENCE_ARCHITECTURE.md) —— 参考架构梳理。

## 功能与产品

- [PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_PLAN.md](PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_PLAN.md) —— 需求主档，里程碑分 M1..M8。
- [GAP_ANALYSIS_AND_ROADMAP.md](GAP_ANALYSIS_AND_ROADMAP.md) —— 差距清单、剩余工作。
- [TECHNICAL_FEATURE_PLAN.md](TECHNICAL_FEATURE_PLAN.md) —— 技术特性维度规划。
- [IMPLEMENTATION_PLAN_P0_P1_P2.md](IMPLEMENTATION_PLAN_P0_P1_P2.md) —— P0/P1/P2 优先级的实现计划。
- [PLUGIN_API.md](PLUGIN_API.md) —— 插件 API（`.minicc/commands/*.md`、MCP）。
- [INTEGRATION_STRATEGY.md](INTEGRATION_STRATEGY.md) —— 多 Lane 合流策略记录。
- [SNAPSHOT_COMPLETION_HARDENING.md](SNAPSHOT_COMPLETION_HARDENING.md) —— 快照完成口径的加固。

## 审计、评测与方法论

- [CONSOLIDATION_REPORT.md](CONSOLIDATION_REPORT.md) —— 分支/worktree 集大成审计：7 个历史分支逐提交判定、23 个测量平面处置、7 个 `consolidated/*` tag 的归并证据。
- [AUDIT_2026-09-20.md](AUDIT_2026-09-20.md) —— 2026-09-20 整体审核：发现的事实 + 修法 + 见证。
- [PROJECT_REVIEW_2026-09-18.md](PROJECT_REVIEW_2026-09-18.md) —— 2026-09-18 阶段性复盘。
- [DEEP_OPTIMIZATION_PLAN.md](DEEP_OPTIMIZATION_PLAN.md) —— 2026-09-18 起草的全自动优化实施计划（A1..CE2：各落一件具体事；状态列全部落齐）。
- [OPTIMIZATION_DELIVERY_2026-09-18.md](OPTIMIZATION_DELIVERY_2026-09-18.md) —— 上述优化方案的收官说明：范围、冲突挑选纪律（不 reset/stash/覆盖别人改的）。
- [BACKEND_OPTIMIZATION_DELIVERY.md](BACKEND_OPTIMIZATION_DELIVERY.md) —— 后端优化交付记录。
- [FRONTEND_HARDENING_DELIVERY.md](FRONTEND_HARDENING_DELIVERY.md) —— 前端/UI 加固交付记录。
- [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) —— 安全清单（密钥、出站网、组件权限）。
- [SPECPROOF_ASSESSMENT.md](SPECPROOF_ASSESSMENT.md) —— 对 SpecProof 参考副本的评估。
- [ONE_FACT_ONE_HOME.md](ONE_FACT_ONE_HOME.md) —— 一事一源方法：术语、字段、类名的唯一家原则。

## 性能与测量

- [PERFORMANCE.md](PERFORMANCE.md) —— 实测过的性能改进与资源治理决策（import 时间、SQLite JSON1 过滤、impact BFS、网关 Redis 缓存、前端对比度门与内容寻址产物）；未经复测的不默认完成。
- [CACHE_AFFINITY_MATRIX.md](CACHE_AFFINITY_MATRIX.md) —— wkapi.pro · gpt-6-sol（冻结）+ 2026-11-16 迁入 `api.aizzz.xyz · gpt-6.1-terra（经 Clash Verge 混合端口 · 直连 403 地理封锁）` 的 prompt_cache_key 亲和实测矩阵（Responses 流/非流报告 cached_tokens；chat/completions 流式不上报、带 key 后上报）——为什么「命中率显示低」是上报面产物而不是缓存失效。
- [CONSOLIDATION_AUDIT.md](CONSOLIDATION_AUDIT.md) —— 分支与工树整合记录：29 工树 → 7；19 个 detached `wt*` 归为 EOL-noise 删除或救援 commit 锚定；7 个 rescue 分支保全内容；远程分支不擅自删。
- [ORACLE_DRAFT.md](ORACLE_DRAFT.md) —— Ch.XLIII《神谕》实时调用存档：温度 0.3 · 输入 4,683 tokens · 输出 178 tokens · `prompt_tokens_details={}`（不回传 cached_tokens）· 所有数字 `/api/digest` 可复核。
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LII《通电》/ Ch.LIII《第十二家灯》/ Ch.LIV《并账》/ Ch.LV《警钟》/ Ch.LVI《会开口的账本》/ Ch.LVII《绿线 / The Green Line》实时调用存档（2026-11-17→11-18，gpt-6.1-terra）：第六条 prompt_cache_key `minicc-chapter-lvii-the-green-line-01`；prompt 5,336 · completion 1,261 · cached_tokens=4,224（共享前缀第十一次现身）·《绿线》取材自 2026-11-17/18 整夜 CI 救火链路（bdf3abcb impact floor → 01a32347 悬空 SHA → 78b2fa6c M8-T543 → 3757d3b5a join-liveness → e358d37 全绿）；本卷章节正文即此存档的渲染结果（含两处生成后机械修订：① 数字随 Atlas 94 / 57 卷同步；② 个别英语片段补水准化文案）。
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LVIII《双峰 / The Two Shards》2026-11-18 人手写定稿（非模型生成）：本日中午 aizzz.xyz 对本账号组停服 `gpt-6.1-terra`（`GET /v1/models` 仍列、单次 ping 被拒，HTTP 404 `model_not_found`）；同 key 同网关同 Clash 127.0.0.1:7897 迁 `gpt-6.1-sol`。v2 套件重跑（n=3 / lane）：pass@1 双 lane 一致 0.667、`tokens_per_success` 185,442 → 79,430（-57%）、p95 306.8s → 74.0s、`repair_attempts` 0.667 → 0；sol prefix cache 双峰：`cached_tokens` 只在 `4,166`（~72.3%，gateway 头缆块）与 `5,446`（~94.7%，warm shard = 头缆 + 本 lane ~1,280）两值间跳，非单调；warm shard ≥ 94% 由 `cache_keeper` 每 220 秒保活。存证正文直接渲染于 almanac Ch.LVIII，双语并存、零 CJK（en 侧）。
- [ORACLE_USAGE.json](ORACLE_USAGE.json) —— 同次调用的 usage 块原样存档（含 model · usage keys · completion_tokens）。
- [GATEWAY_RATELIMIT_LIVE.md](GATEWAY_RATELIMIT_LIVE.md) —— 独立令牌桶实景压测：独立 Redis/RabbitMQ 容器、`/api/changes` 三次爆发各 40 通行/80×429 精确复现、Redis 计数键 `request_rate_limiter.{route}.{ip}.tokens/.timestamp` 已检验（DBSIZE=2）；诚实 fallback=503。
- [LOAD_TESTING.md](LOAD_TESTING.md) —— `scripts/load-test.mjs` 高并发只读端点压力测试的诚实实录（修前 /api/stats p50=43.9s、修后 c=8 p50=3.8s；10 路并发冷磁盘 walk 7.55s；2026-11-16 M8-T1075 / T1086：c=24/64/128 三波累计 33,600 首测 + 25,470 复验 = 59,070 请求 0 非 2xx（2026-11-16 下午复验，warm p95 digest≈150ms；cold cohort 首波 stats p95≈10s 同步 schema 原样记录）；仍属本机诊断而非 SLA）。

## 阅读路径建议

首次：[FIRST_HOUR.md](FIRST_HOUR.md) → [CHANGELOG.md](CHANGELOG.md) → [OPERATIONS.md](OPERATIONS.md)。
若要部署：[SERVICE_PLANE_OPERATOR.md](SERVICE_PLANE_OPERATOR.md)。
若要扩展：[PLUGIN_API.md](PLUGIN_API.md) + [ONE_FACT_ONE_HOME.md](ONE_FACT_ONE_HOME.md)。
若要审计：[AUDIT_2026-09-20.md](AUDIT_2026-09-20.md) + [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)。

- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LIX《现在通了 / The Now Goes Through》2026-11-18 现场存档：单次 chat/completions 调 terra（temperature 0.2 · `response_format=json_object` · prompt 5,072 · completion 1,939 · cached 4,173（82.3%）· 未显式 prompt_cache_key）；zh/en 双字段直接渲染、未经改写；本卷渲染于当晚——Atlas 97 / 卷数 59 / pass@1=1.0。
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LX《破损的引号 / The Broken Quotation》2026-11-18 晚 terra 现场存档：showcase io 页第 599 行内联脚本 `''…` 空引号对——每次加载整段 hydration 炸裂 `SyntaxError: missing ) after argument list`；commit `652bf3c` 删两个字符修复后线上控制台错误 = 0；并行会话缓存交错实测（A/B family 各占 97.6%、互不驱逐）；e2e 两趟口径（71.6% / 48.0%），不以前缀探针冒充 agent 数字；en 侧零 CJK
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXI《并发的风 / The Parallel Wind》2026-11-19 由 StateGraph 锻造台生成并过审：terra 停服后锻造 lane 切 `gpt-6.1-sol`，首次调用即过契约（attempts=1、cached 4,169/5,408、en 零 CJK；zh 1,591/en 2,621 字符）；事实锚点：M8-T1231（交错 A/B）/ M8-T1232（agent 两趟 71.6/48.0）/ M8-T1233（c=6 真并发，零跨 family 驱逐）/ M8-T1234（forge 本身）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXII《按自己的尺度 / On Its Own Scale》2026-11-19 forge-facts 自动取证喂给锻造台：terra 间歇停服期间 `MINICC_MODEL=gpt-6.1-sol` 单次覆盖；首草拟未过契约、attempts=2 修复过审；zh 1,260 / en 2,141 字符、en 零 CJK；Atlas 99 → 100 整数里程碑；事实全从 fact pack 与账本逐字节引用（M8-T1234 / M8-T1235）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXIII《锻造的世界 / The Forged World》2026-11-19 晚 terra 窗口内单次过审（attempts=1，cached 4,154/6,997）；写明 pressure 测试为 fake-provider 环境、不替事实包缺口补写事件；forge 缺键 KeyError 被 M8-T1236 修复并锁定；Atlas 100 → 101（M8-T1234 / T1235 / T1236）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXIV《冶炼的第七日 / The Seventh Day of the Forge》2026-11-19 terra 当晚窗口 attempts=1 首过，en 零 CJK；length contract 被逐字节出言 “zh ≥ 750 字符 / en ≥ 800 字母” 之后由模型遵守（锻造台修复：zh 从 499 补到 1,783 字符）；en 正文显式声明 “the source fact is truncated here, and the ledger does not complete it”；Atlas 101 → 102（M8-T1234 / T1235 / T1236）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXV《水纹的刻度 / The Etched Waterline》2026-11-19，terra 当日停服期间（`Connection error`；sol 系 probe 200，`cached 4,180`）由 `MINICC_MODEL=gpt-6.1-sol` 重跑 attempts=1 首过，en 零 CJK，zh 1,690 / en 4,308 字符；payload `prompt 7,151 · cached 4,152（58.1%）`；`facts_sha256=45227558cf16d74334b648dfbb3fa97a24f8cd66ef35a3740e89f15a8a702fc9`；en 正文把两份快照读数并存（1,994 提交 / 63 卷 vs git log 实况）而不替它们抹平口径；Atlas 102 → 103（M8-T1240）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXVI《回应的按键 / The Click That Answers》2026-11-19，`gpt-6.2-sol` 当晚上线后亲笔，attempts=1 首过（cached 4,153/7,087，58.6%），en 零 CJK，zh 1,354 / en 3,604 字符；事实包 `39f0aaf7f56a610631d5e4e621964d4915ffb393a40a7f2b53b3e5f337da105b`；主题源自当天修好的真 bug：dead button → idle 预注入 + busy 复位（M8-T1242）；Atlas 103 → 104（M8-T1244）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXVIII《一键派发 / One Click, Many Hands》2026-11-19 gpt-6.2-sol attempts=1，`prompt 7,144 · cached 4,152（58.1%）`，en 零 CJK，zh 687 / en 2,246 字符；事实包 `625a24cb145291e8def197310e768e60adec9a9a470f61a6b2c17133e88ae672`；Atlas 105 → 106（M8-T1251）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXIX《活的页面 / The Live Page》2026-11-19 gpt-6.2-sol attempts=1，`prompt 7,725 · cached 4,146（53.7%）`，en 零 CJK，zh 1572 / en 4266 字符；事实包 `e2efb3c45fda7e40d4649b2595ac34d2ec35857db95b5732452b3e6c223202d9`（含 live-wire 实测段）；Atlas 106 → 107（M8-T1252）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXX《没有 bash 的跑道 / The Runner Without Bash》2026-11-19 gpt-6.2-sol attempts=2，`prompt 15,915 · cached 8,288`，en 零 CJK，zh 2262 / en 4507 字符；事实包 `b248e23e59f854f934a3471753260fe8010bd2bdf315b517738a1531ab2af745`（含 live-wire 实测段）；Atlas 107 → 108（M8-T1255）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) — Ch.LXXI《应声的服务面 / The Plane That Answered》2026-11-19 gpt-6.2-sol attempts=1，`prompt 6,974 · cached 4,154`，en 零 CJK，zh 2,357 / en 5,019 字符；事实包 `8084092569af58057eaf3e19e0831b9073d7063aa0bc512ae58a909c6667284c`；Atlas 108 → 109（M8-T1256）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) — Ch.LXXII《过时的断言 / The Stale Assertion》2026-11-19 gpt-6.2-sol attempts=1，`prompt 7,039 · cached 4,153（59.0%）`，en 零 CJK，zh 2,700 / en 4,684 字符；事实包 `3ca511b24542a2b6dda469838f08a1819d9775f0b7d65fe941a0f6e82bde0749`；Atlas 109 → 110（M8-T1258）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) — Ch.LXXIII《验证器说不行 / The Verifier Declines》2026-11-19 gpt-6.2-sol attempts=1，`prompt 7,022 · cached 4,153（59.0%）`，en 零 CJK，zh 1,725 / en 4,074 字符；事实包 `323b6a40c74e49da5bcb750bfda7fa0e4558ae6ac7facb9649fb4ac75eb57fe3`；Atlas 110 → 111（M8-T1260）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) — Ch.LXXIV《红在能力清单那一页 / The Red in the Capability List》2026-11-19 gpt-6.2-sol attempts=1，`prompt 7,025 · cached 4,153（59.0%）`，en 零 CJK，zh 1,632 / en 3,911 字符；事实包 `52a0dddd25b63c213158c7ee5e99ce712f0844f95d22b6dd39ffb220dcb089e9`；Atlas 111 → 112（M8-T1261）
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LXVII《密地图 / The Dense Map》2026-11-19 gpt-6.2-sol attempts=1，`prompt 7,034 · cached 4,153（59.0%）`，en 零 CJK，zh 2,904 / en 6,061 字符；事实包 `cd7aedbfa3bed9b90db5cef3fef79dcbbb00576a66d677db5159ad1369575626`；_WORLD_MAP 与 Atlas 坐标同步到 105（18 panes + 67 almanac + 20 manual），年鉴入 67 卷（M8-T1247）
