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
- [CHAPTER_DRAFT.md](CHAPTER_DRAFT.md) —— Ch.LII《通电》/ Ch.LIII《第十二家灯》实时调用存档（2026-11-17，gpt-6.1-terra）：第二条 prompt_cache_key `minicc-chapter-liii-twelfth-light-01`；prompt 4,977 · completion 851 · cached_tokens=4,224（共享前缀第七次现身）· 模型原生产出的双语段落 HTML-ready；本卷章节正文即此存档的渲染结果。
- [ORACLE_USAGE.json](ORACLE_USAGE.json) —— 同次调用的 usage 块原样存档（含 model · usage keys · completion_tokens）。
- [GATEWAY_RATELIMIT_LIVE.md](GATEWAY_RATELIMIT_LIVE.md) —— 独立令牌桶实景压测：独立 Redis/RabbitMQ 容器、`/api/changes` 三次爆发各 40 通行/80×429 精确复现、Redis 计数键 `request_rate_limiter.{route}.{ip}.tokens/.timestamp` 已检验（DBSIZE=2）；诚实 fallback=503。
- [LOAD_TESTING.md](LOAD_TESTING.md) —— `scripts/load-test.mjs` 高并发只读端点压力测试的诚实实录（修前 /api/stats p50=43.9s、修后 c=8 p50=3.8s；10 路并发冷磁盘 walk 7.55s；2026-11-16 M8-T1075 / T1086：c=24/64/128 三波累计 33,600 首测 + 25,470 复验 = 59,070 请求 0 非 2xx（2026-11-16 下午复验，warm p95 digest≈150ms；cold cohort 首波 stats p95≈10s 同步 schema 原样记录）；仍属本机诊断而非 SLA）。

## 阅读路径建议

首次：[FIRST_HOUR.md](FIRST_HOUR.md) → [CHANGELOG.md](CHANGELOG.md) → [OPERATIONS.md](OPERATIONS.md)。
若要部署：[SERVICE_PLANE_OPERATOR.md](SERVICE_PLANE_OPERATOR.md)。
若要扩展：[PLUGIN_API.md](PLUGIN_API.md) + [ONE_FACT_ONE_HOME.md](ONE_FACT_ONE_HOME.md)。
若要审计：[AUDIT_2026-09-20.md](AUDIT_2026-09-20.md) + [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)。
