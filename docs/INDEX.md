# minicc 文档索引

本仓库的文档不是孤岛。读者从任何一篇入口都应至少能走到其他一篇；这份索引是那扇门。

## 开箱

- [FIRST_HOUR.md](FIRST_HOUR.md) —— 装到第一次成功。按 `--setup` → `--doctor` → `--stats` → `--capabilities` → `--version` → 首次进模型的顺序展开，每步实测。
- [CHANGELOG.md](CHANGELOG.md) —— 2026-09-20 至今合流记录；M1..M8 的落成面、批次 686–742、已知边界（CI-only packaging 门、nightly 跳过）。

## 运行与自检

- [OPERATIONS.md](OPERATIONS.md) —— 运维和自检手册：`--setup`、`--doctor`、`--doctor-strict`、`--stats`、`--version --json` 的语义与退出码契约，网络访问前提，状态目录规则，`--json` 各 flavor 的键形状。
- [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) —— 评测面：任务套件结构、grading_coverage 的两个自报口径、nightly 绝对门的环境变量。

## 在线接口与服务面

- [SERVICE_PLANE_PLAN.md](SERVICE_PLANE_PLAN.md) —— 服务面规划（P1..P5），registry / config / inspector / tasks 五模块的角色与边界。
- [SERVICE_PLANE_OPERATOR.md](SERVICE_PLANE_OPERATOR.md) —— 服务面运维：standalone 启 tasks、SQLite 只读、curl 实录（含 999-limit 被钳后的 `X-Minicc-Tasks-Limit: 100`）、Compose。
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

- [AUDIT_2026-09-20.md](AUDIT_2026-09-20.md) —— 2026-09-20 整体审核：发现的事实 + 修法 + 见证。
- [PROJECT_REVIEW_2026-09-18.md](PROJECT_REVIEW_2026-09-18.md) —— 2026-09-18 阶段性复盘。
- [BACKEND_OPTIMIZATION_DELIVERY.md](BACKEND_OPTIMIZATION_DELIVERY.md) —— 后端优化交付记录。
- [FRONTEND_HARDENING_DELIVERY.md](FRONTEND_HARDENING_DELIVERY.md) —— 前端/UI 加固交付记录。
- [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) —— 安全清单（密钥、出站网、组件权限）。
- [SPECPROOF_ASSESSMENT.md](SPECPROOF_ASSESSMENT.md) —— 对 SpecProof 参考副本的评估。
- [ONE_FACT_ONE_HOME.md](ONE_FACT_ONE_HOME.md) —— 一事一源方法：术语、字段、类名的唯一家原则。

## 阅读路径建议

首次：[FIRST_HOUR.md](FIRST_HOUR.md) → [CHANGELOG.md](CHANGELOG.md) → [OPERATIONS.md](OPERATIONS.md)。
若要部署：[SERVICE_PLANE_OPERATOR.md](SERVICE_PLANE_OPERATOR.md)。
若要扩展：[PLUGIN_API.md](PLUGIN_API.md) + [ONE_FACT_ONE_HOME.md](ONE_FACT_ONE_HOME.md)。
若要审计：[AUDIT_2026-09-20.md](AUDIT_2026-09-20.md) + [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)。
