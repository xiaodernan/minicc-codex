# 服务面（Service Plane）现状与分阶段计划

> 制定日期：2026-11-09。基线：`main`（本文件所在提交）。配套代码：`minicc-cloud/`。
> 本文是**代码旁的计划文档**：它只写目标、验收命令与扩展方向；每一次读数的批次记录仍写到
> `docs/ROADMAP_TO_PRODUCT.md`（那份文档是账本，这份是地图）。

## 一、为什么是「服务面」而不是重写

`minicc` 的引擎是一个 Python 进程：`minicc/web.py` 已经有 HTTP 入口、任务库、租约与 worker。
把引擎改写成 Java 不会让它更可信，只会把已验证的不变量（租约栅栏、变更审计、证据链）复制一份
未经检验的实现。所以这里只做**配套的服务化外壳**：注册、网关、配置、只读检查服务，全部通过
一个显式桥接层（`minicc-cloud-bridge`）调用既有的 Python 工具，而不是重新实现它们。

三条硬约束：

1. **只读优先**：`minicc-cloud-inspector` 只读工作区（`MINICC_ALLOWEDROOTS` 之外一律拒绝），
   不提供写入口；写路径仍由 Python 侧的权限模型与审计负责。
2. **一个事实一个家**：服务发现走 Eureka、配置走 Config Server、跨服务预算写在共享
   `config-repo/application.yml`；服务自身不再复制同一批数字。
3. **可离线验证**：所有模块的测试都不需要外网、不需要真实注册中心（`mvn test` 在空环境全绿）。

## 二、当前状态（2026-11-09 实测；2026-11-10 增补 insights）

| 项 | 状态 | 证据 |
| --- | --- | --- |
| `minicc-cloud-bridge` | 有代码、有测试 | `MiniccBridge` 起 Python 子进程；`ChangeInspectorClient` 管超时与失败原因 |
| `minicc-cloud-registry` | Eureka Server，8761 | 单类应用 + `application.yml` |
| `minicc-cloud-config` | Config Server（native），8888 | 共享 `config-repo/application.yml` + 每服务一份；网关与检查服务 `optional:` 导入 |
| `minicc-cloud-inspector` | 只读变更服务，8081 | 工作区守卫 + 桥接失败建议（`BridgeFailureAdvice`） |
| `minicc-cloud-tasks` | 只读任务历史，8082 | 挂载真实 `.minicc/` 只读；文件名 API 默认对齐 Python 的 `tasks.sqlite3`（2026-11-10 漂移修） |
| `minicc-cloud-insights` | 只读聚合洞察，8087 | P6，2026-11-10 新增：总数 exact、分状态 capped、audit 行数 capped；docker-compose 已接入 |
| `minicc-cloud-gateway` | Spring Cloud Gateway，8080 | `lb://` 路由（含 `/api/insights/**`）+ Resilience4j 熔断 + 回退端点 |
| 编排 | `docker-compose.yml` 六服务 | registry → config → inspector/tasks/insights → gateway 健康依赖链 |
| Java 测试 | 全绿 | `mvn -B test` 退出码 0（2026-11-10 实测：8 模块全绿，insights 12/12） |
| Python 侧 | 不受影响 | 服务面只新增文件；`tests/fence_rosters/wide.txt` 已按门要求加宽 |

分支与工作树处置（同日实测）：

- `main` 是唯一集成线；`feature/minicc-cloud` 已合入（两次合流：骨架 M8-T717、配置中心 M8-T719）。
- `origin/m8-t537`、`origin/integration/m8-t537-to-main` 的提交已全部在 `main` 里（未合并计数 0）。
- `dev/minicc-reliability-4ba3` 与本仓**没有共同祖先**（独立 `git init` 平面，51 个提交，
  657 个文件），因此**不做整树合并**：它的内容以「车道接管」方式逐项落入 `main`
  （外来章节门、p95 劣化读数等）。该分支与远端分支保留，任何一方的工作都没有删除。
- 22 个 `wt*`/`plane*` 工作树是**测量平面**（举证用的冻结检出）。它们的 HEAD 提交或者
  已在 `main` 历史里，或者是独立的单提交导出平面。删除它们等于销毁测量证据，故**保留**，
  不再作为开发分支使用。

## 三、分阶段计划

每一阶段都以「一条命令能判红绿」结尾；没有读数的阶段不算完成。

### P1 配置与可观测（已完成，M8-T721）

目标：配置中心成为唯一数字来源，服务不再各自写死预算。

改动：网关的 `response-timeout` 与熔断超时改读 `minicc.cloud.gateway.*`；检查服务的 Python
预算改读 `minicc.cloud.inspector.timeout-seconds`；`/actuator/configprops` 暴露生效值。

验收：把 `config-repo` 里的超时从 40 改到 5，重启网关后 `curl :8080/actuator/configprops`
读到 5；`mvn test` 仍全绿；无配置中心时服务仍能启动（`optional:` 路径）。

扩展：配置变更推送（Spring Cloud Bus）留到有第二个实例时再做，单实例下轮询没有收益。

### P2 只读任务服务（Task Service）（已完成，M8-T724）

目标：把「看一个工作区现在是什么状态」变成可水平扩展的只读服务。

落地：`minicc-cloud-tasks`，8082。JDBC URL 固定 `mode=ro`，每条连接再执行
`PRAGMA query_only=ON` 兜底；库文件不存在返回 503 并写明路径（不返回空数组装成「没有任务」）；
未知 id 返回 404；损坏快照返回 500 并说明是快照损坏；列表只回 `task_id/status/created_at/
workspace_path/preview`，截断由 `X-Minicc-Tasks-Truncated` 头声明。网关新增 `/api/tasks/**`
路由与 `tasks-route` 熔断。

改动：新增 `minicc-cloud-tasks`，暴露工作区清单、任务快照只读视图；数据来源是 Python 侧
`minicc --stats` 与 `task_store` 的只读查询，不做任何写入。

验收：无工作区权限时返回 403 而不是 500；对一个 1000 文件的工作区，P95 < 500ms（本机实测）；
`mvn test` 全绿；网关为它增加一条 `lb://` 路由且有回退端点。

扩展：只读视图稳定后，再讨论「提交任务」——那需要先复刻 Python 侧的权限与审计语义。

### P3 Java 侧进入 CI（已完成，M8-T723）

目标：服务面不再靠人手跑 `mvn test`。

落地：`ci.yml` 新增 `java-tests` job（Temurin 21 + Maven 缓存），范围判定用
`git diff --quiet <base> HEAD -- minicc-cloud`：Python-only 的推送不付第二套工具链的时长，
跳过时打 notice 而不是假装跑过。

实测：T723 那次推送同时改了 `minicc-cloud/README.md`，CI run `42622752864` 整体
**success（24m46s）**——`java-tests` 因此真实执行并绿；T714 之后那些只改 Python 的运行里
该 job 记为跳过（notice 可见）。

改动：新增独立 workflow job：JDK 21 + Maven 缓存，`mvn -B -q test`，只在该目录变化时触发。

验收：故意让一个断言失败 → job 变红；还原 → 变绿；主 Python job 的时长不受影响。

扩展：镜像构建留到发布流程，CI 只验证可构建。

### P4 边界与凭据（已完成，M8-T727）

目标：服务面不能成为绕过 Python 权限模型的旁路。

落地：凭据脱敏放在 `BridgeResponse` 的紧凑构造器里——每一次失败都经 `failureReason()`
引用 stderr，所以这里是唯一咽喉，调用方无法忘记、也无法各写一份；stdout 不动（那是要解析的
数据，改写会破坏它）。检查服务的 `minicc.allowed-roots` 由 `config-repo` 下发，本地只剩
`${MINICC_ALLOWEDROOTS:}` 空默认；网关 `inspector-changes`/`tasks` 两条路由挂 `RequestSize`，上限读共享键 `minicc.cloud.gateway.max-request-bytes`（1 MiB）（P6 增 `insights` 后共三条，参数同）。

实测：红证是 `Expecting actual: "MINICC_API_KEY=sk-..." to contain: "[redacted]"`；加上脱敏后
`mvn -B test` 全绿（7 模块 74 用例，0 失败 1 跳过）。网关 413 用 WebTestClient 真打出来，
不是只断言路由定义。脱敏正则初版对 1 MiB 单行 stderr 有灾难性回溯，已改为行首/空白锚定。

### P5 集大成：能力目录（已完成，M8-T729）

目标：把 `minicc` 的能力（变更检查、证据门、任务历史、评测读数）收成一份机器可读目录，
由服务面暴露，供 UI 与外部调用方发现。

落地：Python 侧新增 `--capabilities`（`minicc.main`，打印 JSON 后退出 0，刻意不加载 MCP
管理器——发现会拉起外部进程，目录必须只读离线）；条目直接来自 `build_registry`，没有第二份
名单。Java 侧 `/api/capabilities` 只做转发与形状校验：子进程失败、超时、输出不是合法 JSON
分别映射到 503 并在 body 里说明是哪一种，绝不返回空的 `tools` 冒充「没有能力」。

实测：`minicc --capabilities --json` 输出 `count=23`，与注册表键集合逐条相等（新测试
`tests/test_capabilities_names_every_registered_tool.py` 断言）；Python 侧
32 passed；`mvn -B test` EXIT=0。换一个 stub 脚本把 payload 换掉，端点跟着变——Java 里
没有任何工具名或数量。

### P6 只读聚合洞察（已完成，M8-T770）

目标：给 UI/外部调用方一个"引擎现在长什么样"的一次性答案——任务分状态、审计条数——不需要 Python CLI、不落 Java 一行写逻辑。

落地：新模块 `minicc-cloud-insights`（**8087**——本机 8083 已被另一个项目的 listener 占用，未动其进程；8083 曾是它的初值）。Eureka Client + 可选 `configserver`（共享处不复制数字；`minicc.cloud.insights.*` 落在 `config-repo/minicc-cloud-insights.yml`）。读 `tasks.sqlite3`（`mode=ro` + `PRAGMA query_only=ON`）：总数 exact（`COUNT(*)`）、分状态计数 capped 于 `max-scan-rows`（默认 10000）、`MIN/MAX(created_at)` 两个时间戳；`audit.jsonl` 行数 capped 于 `max-audit-lines`（默认 100000）。`audit.jsonl` 缺失 → `present: false`（不视为故障，首小时常态）；存在但不可读 → 503。不可解析的快照 → 500 并点名坏快照的 `task_id`（与 tasks 服务同款语法）。网关 `/api/insights/**` 路由 + `insights-route` Resilience4j breaker + 独立 `/fallback/insights`（503+reason）。docker-compose 接入（六服务健康链）。Python 侧不感知。

实测：`mvn -B test` 全绿（8 模块；insights 12/12）。standalone 真跑探针（不碰真实 `.minicc/`，JDK 25）：`GET /api/insights/summary` → `{"tasks":{"total":3,"by_status":{"queued":1,"completed":2},"scan_truncated":false,...},"audit":{"present":true,"lines":3,...}}`；`?workspace=/other` → `total:1`；`actuator/health` 200。

扩展：insights 滚动快照镜像（`/api/insights/history`）+ Config Bus 热刷新上限；过一遍 bridge 的 memory budget 验证insights 对大库 SQL 的行为。

### P7 进程预算与同命令合并（已完成，M8-T841）

目标：检查服务每回答一个请求就启动一个 Python 解释器。突发 N 个请求就是 N 个解释器抢同一批核心；
同一页面并发轮询两个面板问同一个问题时，每个面板各付一次解释器启动。这一层此前既没有并发上限，
也没有请求合并。

落地：`minicc-cloud-bridge` 新增 `CommandRunner` 接缝与 `GovernedRunner`——(1) 进程预算是**服务级**的
（`minicc.max-processes`，未设时取 `min(8, max(2, 核数))`），由 `BridgeConfiguration` 建一个、两个
客户端共用，避免「每个客户端一份配额」把上限乘二；(2) 同 argv 的并发调用合并成一次子进程，合并键用
**长度前缀编码**而不是分隔符拼接——`["a","b"]` 与 `["a\0b"]` 不能撞键；(3) 等不到配额时返回带原因的
失败，绝不返回空结果（空变更列表读作「工作区干净」）；(4) 合并只发生在并发窗口内，顺序的下一次调用
一定重新执行，不是缓存。

顺带修掉一处静默的边界损坏：Windows 上 JDK 给子进程参数加引号却不转义参数**内部**的双引号，MSVCRT
因此提前结束引号段——实测 `print('{"ok": true}')` 到达子进程时变成 `print('{ok: true}')`，退出码 0、
输出看似合理、程序已经换了一个。现在含双引号的 `-c` 脚本改走 stdin（无引号层），`-` 与 `-c` 同样
占据 `argv[0]`，调用方的 `sys.argv[1:]` 不变。

实测：`GovernedRunnerTest` 7 门（8 个调用者共享 1 次执行、不同命令不共享、含分隔符的参数不撞键、
6 并发峰值恰为 2、拿不到配额时报原因、失败不留在去重表、非法参数拒绝构造）；`BridgedBurstTest`
用真实 Python 子进程计数——8 个并发调用者留下 **1** 行启动记录，随后的一次独立调用留下 **2** 行
（合并≠缓存）；`BridgeScriptDeliveryTest` 3 门钉住脚本逐字节到达与 argv 下标不变。

## 四、再往后可以做什么（保证永远有下一步）

- 评测读数的只读服务：把 `--suite v2` 的结果变成可查询的时间序列。
- 证据门的远程执行：同一套 checker 在 CI 与服务里读同一份语料。
- 多工作区并发：检查服务按工作区做缓存与配额，先量 P95 再谈并发度（进程预算与同命令合并已由 P7
  落地；剩下的是按工作区配额与 P95 实测）。
- 服务面自己的「一个事实一个家」门：扫描 `application.yml` 与 `config-repo` 的重复键。

## 五、怎么运行

```
cd minicc-cloud
mvn -B test                 # 四个模块的测试，不需要外网
mvn -DskipTests package     # 产出可运行 jar
docker compose build        # 需要先 package
docker compose up           # registry → config → inspector → gateway
curl http://localhost:8888/minicc-cloud-gateway/default   # 配置中心读到什么
curl http://localhost:8080/api/changes?workspace=/workspaces/target
```
