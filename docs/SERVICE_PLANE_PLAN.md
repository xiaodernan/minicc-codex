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

## 二、当前状态（2026-11-09 实测）

| 项 | 状态 | 证据 |
| --- | --- | --- |
| `minicc-cloud-bridge` | 有代码、有测试 | `MiniccBridge` 起 Python 子进程；`ChangeInspectorClient` 管超时与失败原因 |
| `minicc-cloud-registry` | Eureka Server，8761 | 单类应用 + `application.yml` |
| `minicc-cloud-config` | Config Server（native），8888 | 共享 `config-repo/application.yml` + 每服务一份；网关与检查服务 `optional:` 导入 |
| `minicc-cloud-inspector` | 只读变更服务，8081 | 工作区守卫 + 桥接失败建议（`BridgeFailureAdvice`） |
| `minicc-cloud-gateway` | Spring Cloud Gateway，8080 | `lb://` 路由 + Resilience4j 熔断 + 回退端点 |
| 编排 | `docker-compose.yml` 四服务 | registry → config → inspector → gateway 的健康依赖链 |
| Java 测试 | 全绿 | `mvn -B test` 退出码 0（bridge/gateway/config/inspector 四模块） |
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
跳过时打 notice 而不是假装跑过。验收仍待一次真实触碰 `minicc-cloud/` 的推送读数。

改动：新增独立 workflow job：JDK 21 + Maven 缓存，`mvn -B -q test`，只在该目录变化时触发。

验收：故意让一个断言失败 → job 变红；还原 → 变绿；主 Python job 的时长不受影响。

扩展：镜像构建留到发布流程，CI 只验证可构建。

### P4 边界与凭据

目标：服务面不能成为绕过 Python 权限模型的旁路。

改动：检查服务的允许根目录从环境变量改为配置中心下发；网关增加请求大小与路径白名单；
桥接层对 Python 侧 stderr 做脱敏后再回传。

验收：越界路径 403；超限请求 413；回传体里不出现任何形如密钥的串（用产品自己的脱敏词表断言）。

扩展：mTLS 只在多机部署时才有意义，单机 compose 下不做。

### P5 集大成：能力目录

目标：把 `minicc` 的能力（变更检查、证据门、任务历史、评测读数）收成一份机器可读目录，
由服务面暴露，供 UI 与外部调用方发现。

改动：`minicc-cloud-inspector` 增加 `/api/capabilities`；条目来自 Python 侧注册表，
不手写第二份名单。

验收：目录条目数与 Python 注册表逐条相等；新增一个能力不改 Java 代码就能出现在目录里。

## 四、再往后可以做什么（保证永远有下一步）

- 评测读数的只读服务：把 `--suite v2` 的结果变成可查询的时间序列。
- 证据门的远程执行：同一套 checker 在 CI 与服务里读同一份语料。
- 多工作区并发：检查服务按工作区做缓存与配额，先量 P95 再谈并发度。
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
