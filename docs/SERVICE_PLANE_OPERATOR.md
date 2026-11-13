# minicc-cloud 服务面运维手册

> 全局索引：[INDEX.md](INDEX.md)。

这份文档讲一件事：**怎么把服务面运行起来、它到底答了什么、验证依据是什么。**

以下命令都在本仓库 `main@393b4f7`（含 M8-T721..T731 合流；M8-T732 README 服务面指针）上实测；输出原文来自实机 curl/Invoke-WebRequest。

## 1. 模块拓扑与端口

| 模块 | 端口 | 职责 |
| --- | --- | --- |
| `minicc-cloud-registry` | 8761 | Eureka 服务发现 |
| `minicc-cloud-config` | 8888 | Config Server（native），`config-repo/` 下的共享/服务专属 yml |
| `minicc-cloud-inspector` | 8081 | 只读工作区诊断：`/api/changes`、`/api/capabilities` |
| `minicc-cloud-tasks` | 8082 | 只读任务历史（SQLite `tasks.sqlite3`），`db` 来自 `MINICC_STATE` |
| `minicc-cloud-insights` | 8087 | 只读聚合洞察：`/api/insights/summary`（任务总数/分状态、audit 行数），`db`/`audit` 来自 `MINICC_STATE` |
| `minicc-cloud-gateway` | 8080 | 路由 + Resilience4j 熔断，`/api/changes`、`/api/tasks*`、`/api/insights/*` |
| `minicc-cloud-bridge` | —（库） | 生命周期管理 Python 子进程，凭据脱敏 |

服务面不重写 Python 引擎；桥接层是唯一缝隙。`mvn -B test` 覆盖七个模块；CI 的 `Service plane tests (mvn)` 只在 `minicc-cloud/**` 改动时触发。

## 2. 验证 tasks 服务：standalone 模式

以下步骤已逐步跑通；被测环境为 JDK 25 + Maven 3.9，全部在本机对话中执行：

```powershell
# 1. 造一个探针用的 tasks.sqlite3（绝不读写真实 .minicc/）
python - <<'PY'
import sqlite3, json, pathlib
root = pathlib.Path(r'C:\path\to\probe')
root.mkdir(parents=True, exist_ok=True)
db = root / 'tasks.sqlite3'
conn = sqlite3.connect(str(db))
conn.execute('CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, created_at DOUBLE, workspace_path TEXT, payload TEXT)')
payload = {'task_id': 't-demo-1', 'status': 'completed', 'preview': 'demo task', 'created_at': 1762720000.0}
conn.execute('INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?)', ('t-demo-1', 1762720000.0, '/tmp/ws-demo', json.dumps(payload, ensure_ascii=False)))
conn.commit()
conn.close()
PY

# 2. 启动（config server 未启动时不影响本机返回；以 standalone 运行）
cd minicc-cloud\minicc-cloud-tasks
set MINICC_STATE=C:\path\to\probe
mvn spring-boot:run
```

启动日志出现 `Started TasksApplication in ... seconds` 即可。容器读取 `${MINICC_STATE}/tasks.sqlite3`（表 `tasks`：`task_id TEXT PRIMARY KEY, created_at DOUBLE, workspace_path TEXT, payload TEXT`）；`mode=ro` 打开。

## 3. 三种调用实录

```text
GET http://127.0.0.1:8082/api/tasks?limit=5
```

```
HTTP 200
[{"task_id":"t-demo-1","status":"completed","created_at":1.76272E9,"workspace_path":"/tmp/ws-demo","preview":"demo task for the service-plane operator guide"}]
```

```text
GET http://127.0.0.1:8082/api/tasks/t-demo-1
```

```
{"task_id":"t-demo-1","created_at":1.76272E9,"workspace_path":"/tmp/ws-demo","payload":{"task_id":"t-demo-1","status":"completed","preview":"demo task for the service-plane operator guide","created_at":1.76272E9}}
```

`limit` 超过服务端天花板：

```
GET http://127.0.0.1:8082/api/tasks?limit=999

StatusCode: 200
X-Minicc-Tasks-Truncated: true
X-Minicc-Tasks-Limit: 100
[{"task_id":"t-demo-1", ...}]
```

响应头 `X-Minicc-Tasks-Truncated: true` 表明被截断；`X-Minicc-Tasks-Limit: 100` 表明生效天花板来自 Config Server 的 `minicc-cloud-tasks.yml`（`spring.cloud.config.import: optional:configserver:${CONFIG_SERVER:...}`），本地 standalone 时由 `MINICC_TASKS_MAX_LIMIT` 环境变量或 `100` 兑底。

### insights（8087 实测，2026-11-10）

探针库：`/probe` 下 `tasks.sqlite3`（3 行：completed×2、queued×1）+ `audit.jsonl`（3 行）。不接触真实 `.minicc/`。

```text
GET http://127.0.0.1:8087/api/insights/summary

HTTP 200
{"generated_at":"2026-11-10T12:50:49.921375800Z","tasks":{"present":true,"total":3,
 "by_status":{"queued":1,"completed":2},"scan_truncated":false,
 "min_created_at":1.76272E9,"max_created_at":1.7627202E9,"workspace":null},
 "audit":{"present":true,"lines":3,"truncated":false,"capped_at":100000}}

GET http://127.0.0.1:8087/api/insights/summary?workspace=/other

HTTP 200
{… "total":1, "by_status":{"completed":1}, "workspace":"/other"} …
```

总数走 `COUNT(*)`（不截断），分状态计数超过 `MINICC_INSIGHTS_MAX_SCAN_ROWS` 时返回 `scan_truncated: true`；audit 超过 `MINICC_INSIGHTS_MAX_AUDIT_LINES` 时 `truncated: true`。未设 audit 或文件不存在时 `audit.present: false`——**不视为故障**（首小时没有审计是正常状态）；文件不可读才是 503。

## 4. 环境变量契约

### tasks（`minicc-cloud-tasks`）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `MINICC_STATE` | `../.minicc` | `tasks.sqlite3` 所在目录 |
| `MINICC_TASKS_MAX_LIMIT` | `100` | 客户端 `limit` 服务端天花板（standalone） |
| `CONFIG_SERVER` | `http://localhost:8888` | 可选；未启动时按 standalone |
| `EUREKA_ZONE` | `http://localhost:8761/eureka/` | 可选；未启动 `Registration failed` 警告后 standalone |

### insights（`minicc-cloud-insights`）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `MINICC_STATE` | `../.minicc` | `tasks.sqlite3` / `audit.jsonl` 所在目录 |
| `MINICC_INSIGHTS_MAX_SCAN_ROWS` | `10000` | 分状态计数的扫描天花板（standalone），`COUNT(*)` 总数不受此限 |
| `MINICC_INSIGHTS_MAX_AUDIT_LINES` | `100000` | audit 行数计数的硬上限（standalone），超限返回 `truncated: true` |
| `CONFIG_SERVER` | `http://localhost:8888` | 可选；未启动时按 standalone |
| `EUREKA_ZONE` | `http://localhost:8761/eureka/` | 可选；未启动 `Registration failed` 警告后 standalone |

### inspector（`minicc-cloud-inspector`）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `MINICC_ALLOWEDROOTS` | `/workspaces` | 路径准入白名单；外面一律拒绝 |
| `EUREKA_ZONE` | `http://localhost:8761/eureka/` | 可选 |
| `CONFIG_SERVER` | `http://localhost:8888` | 可选 |
| `MINICC_BRIDGE_CMD` | 自动 | Python CLI 调用方式（例如 `python -m minicc`） |

### gateway（`minicc-cloud-gateway`）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `EUREKA_ZONE` | `http://localhost:8761/eureka/` | 寻址 inspector / tasks |
| `CONFIG_SERVER` | `http://localhost:8888` | 可选；可覆写 `response-timeout-seconds` / `connect-timeout-ms` |

## 5. 故障排查

- Q：`TaskStoreUnavailableException` →「任务库读取失败」
  A：`MINICC_STATE` 没指到 `tasks.sqlite3` 目录，或文件不存在/损坏。建文件或修正 `MINICC_STATE`。
- Q：curl 返回 404
  A：`{taskId}` 不在库里。任务 ID 由 Python 引擎在 `minicc/task_manager.py` 生成，手填必 404。
- Q：`limit` 被静默钳到 100
  A：`X-Minicc-Tasks-Limit: 100` 就是这个语义；把 `MINICC_TASKS_MAX_LIMIT` 或 Config Server 放大。
- Q：日志 `Registration failed ... Connection refused`
  A：Eureka 不可达。服务面 standalone 模式不依赖注册中心，所有 API 仍可用。
- Q：inspector 返回空数组
  A：只读 `ALLOWEDROOTS` 外路径无法诊断；设置 `MINICC_ALLOWEDROOTS` 白名单，或改挂 `/workspaces/target:ro`。

## 6. Full stack（Docker Compose，实测 2026-11-13，M8-T862）

八个容器：`minicc-cloud-{registry,config,inspector,tasks,insights,gateway}` + Redis 7-alpine + RabbitMQ 3-alpine。compose 已参数化端口（缺省即默认 8761/8888/6379/5672/15672/8080/8082/8087，**本机这几个端口全被其他项目占了，实测用下面的值覆盖**）：

```powershell
set MINICC_CLOUD_REGISTRY_PORT=18762
set MINICC_CLOUD_CONFIG_PORT=18888
set MINICC_CLOUD_REDIS_PORT=16379
set MINICC_CLOUD_RABBITMQ_PORT=55672
set MINICC_CLOUD_GATEWAY_PORT=18080
# 可选：慢挂载（Windows→Docker bind）时同时放宽两个 Python/Java 预算
set MINICC_CLOUD_INSPECTOR_TIMEOUTSECONDS=300
set MINICC_CLOUD_GATEWAY_RESPONSETIMEOUTSECONDS=300
set MINICC_GIT_STATUS_TIMEOUT_SECONDS=240
mvn -DskipTests package -f minicc-cloud/pom.xml
docker compose -f minicc-cloud/docker-compose.yml build        # ~6 分钟
docker compose -f minicc-cloud/docker-compose.yml up -d
```

实测（2026-11-13）全部 **healthy**：registry/config/redis/rabbitmq/inspector/tasks/insights/gateway。

```text
$ curl http://127.0.0.1:18080/api/health/all
{"upCount":3,"totalServices":3,"services":[
  {"upstreamStatus":"UP","service":"minicc-cloud-insights"},
  {"upstreamStatus":"UP","service":"minicc-cloud-inspector"},
  {"upstreamStatus":"UP","service":"minicc-cloud-tasks"}]}

$ curl "http://127.0.0.1:18080/api/changes?workspace=/workspaces/target"   # 挂载 mini probe repo
{"partial":false,"reasons":[],"summary":{"files":[...3 files...],"totalFiles":3,
 "additions":6,"deletions":4}}        http 200, time 1.85s（CircuitBreaker 半开自愈后）

$ curl http://127.0.0.1:18080/api/cached/inspector/status   # Redis 真写真读
{"service":"inspector","upstreamStatus":"UP"}
# 扑过 fanout 失效消息后：docker exec minicc-cloud-redis-1 redis-cli KEYS 'gateway-routes*'
# → 失效前 "gateway-routes::inspector:status"
# → 失效后 (empty array)     —— 热缓存被真正 fanout 清掉了
```

**几个本机实测教训（都是踩出来的）**：
- 端口被占就换一个：上面 16379/55672/18080 都是为避开 `docker.backend` / `wslrelay` 选的。
- `rabbitmq:3-management-alpine` 在这里永远 `.erlang.cookie: eacces`（容器 uid 不匹配）；`rabbitmq:3-alpine` 正常——composer 已改用它。
- inspector 若基于 jammy 的 Python（3.10），`minicc/clock.py` 的 `datetime.UTC` 直接 ImportError（需要 **Python ≥ 3.11**）；compose 已改用 `eclipse-temurin:21-jre-noble`（Ubuntu 24.04，自带 Python 3.12）。
- Eureka registry 在每次容器 recreate 后短暂列出 DOWN 残留（例如 `MINICC-CLOUD-INSPECTOR -> [DOWN, UP]`）；这是**正常的服务端真实状态**（上次跑挂的实例还没被驱逐），LB 会按 UP 过滤，约 90s 后 Registry 自然驱逐。
- 一个大 repo（本仓，>100 MB / NTFS bind-mount）上 `git status` 可超过 120 秒：放宽 `MINICC_CLOUD_INSPECTOR_TIMEOUTSECONDS` / `MINICC_GIT_STATUS_TIMEOUT_SECONDS` 才能用，或在原生 Linux 上跑（那本来就是推荐方式）。
- tasks / insights 是**有效地 healthy 但 503**：DB（`.minicc/tasks.sqlite3`）在全新工作区是空的；两服务都把 503 + 原因返回("洞察库读取失败 ... [SQLITE_CANTOPEN]" / "任务库读取失败")，不是崩了——这是诚实契约。

仅解析不启动：`docker compose -f minicc-cloud/docker-compose.yml config --quiet`（rc=0 无错）。已验证。

## 7. 聚合健康面与 lb://（实测 2026-11-13，M8-T850）

`/api/health/all` 是网关给出的单一全景端点。下面是 2026-11-13 在本机实测的完整链路：
registry 起 8761、insights 起 8087（已注册为 Eureka `MINICC-CLOUD-INSIGHTS` 实例），网关起 8411
（8080 被 Docker 占，改用 `SERVER_PORT=8411`），`/api/health/all` 回答：

```json
{"totalServices":3,"upCount":1,
 "services":[
   {"upstreamStatus":"UNKNOWN","service":"minicc-cloud-inspector"},
   {"upstreamStatus":"UNKNOWN","service":"minicc-cloud-tasks"},
   {"upstreamStatus":"UP","service":"minicc-cloud-insights"}]}
```

驱动此结果的命令（执行序）—— 本例是在本机真实运行的，不是 mock：

```powershell
# 1. registry stand-alone
set SERVER_PORT=18761                       # 8761 被占时改用 18761
java -jar minicc-cloud-registry-0.1.0.jar   # nothing - it will block
# 验证
curl http://127.0.0.1:18761/actuator/health     # {"status":"UP","groups":["liveness","readiness"]}
curl -H 'Accept: application/json' http://127.0.0.1:18761/eureka/apps
# -> {"applications":{"versions__delta":"1","apps__hashcode":"","application":[]}}

# 2. insights stand-alone
set MINICC_STATE=D:\path\to\.minicc
set SERVER_PORT=8087
java -jar minicc-cloud-insights-0.1.0.jar

# 3. gateway on another port, pointed at the registry
set SERVER_PORT=8411
set SPRING_RABBITMQ_LISTENER_SIMPLE_AUTO_STARTUP=false   # no local broker; drop the listener
set EUREKA_ZONE=http://127.0.0.1:18761/eureka/           # or the default 8761 when free
java -jar minicc-cloud-gateway-0.1.0.jar

# 4. the answer
curl http://127.0.0.1:8411/api/health/all
```

结论：registry discovered MINICC-CLOUD-INSIGHTS and MINICC-CLOUD-GATEWAY (instance 1), tasks and
inspector were not started (hence `UNKNOWN`),
and the aggregate endpoint counted exactly the one that answered (`upCount: 1`) — 不把"没人知道"报成 UP。

## 8. opt-in 实机集成探针（本机练习，不进 CI）

三个环境变量控制"跑真 broker / 真 server"的测试；不设则自动 skip，CI 不受影响：

| 环境变量 | 测试 | 需要的东西 | 验证什么 |
| --- | --- | --- | --- |
| `MINICC_TEST_REDIS_URL` | `tests/test_redis_cache.py::test_redis_live_backend_roundtrip`（Python）<br>`tests/test_redis_cache.py::test_stats_live_path_increments` | 一个 Redis（`redis:7-alpine` 即可） | minicc 的分布式缓存跨进程 set/get、TTL 过期、namespace 隔离、`stats()` 计数器活增量 |
| `MINICC_TEST_RABBIT_URI` | `CacheInvalidationRoundTripLiveTest`（网关） | 一个 RabbitMQ（`rabbitmq:3-alpine` 即可） | 缓存失效消息真正穿过 `minicc.gateway.route.refresh` fanout exchange：body=服务名、header `route`=规范键 |

探针步骤示例（本机）：

```powershell
docker run -d --name minicc-rabbit-probe -p 5673:5672 rabbitmq:3-alpine
$env:MINICC_TEST_RABBIT_URI = 'amqp://guest:guest@127.0.0.1:5673'   # 注意：无尾部斜杠；vhost 缺省 "/"
mvn -Dtest='CacheInvalidationRoundTripLiveTest' test                # Tests run: 1, Skipped: 0
Remove-Item Env:MINICC_TEST_RABBIT_URI
docker stop minicc-rabbit-probe; docker rm minicc-rabbit-probe
```

探针测试与其他测试的区别：它们直接连 broker（不启动 Spring ApplicationContext，不触发
`RabbitAdmin` 的 `afterPropertiesSet` 在缺 broker 时拖垮上下文），所以不设变量时零连接尝试、零副作用。

## 9. `fetchedAtMs` 与 /actuator/info build 消息（M8-T868/T869）

两个常见问号与它们的答案隔一个字段就到了，不用再起 Redis CLI：

**Q：`/api/cached/inspector/status` 答出来的 `UP` 到底是 live 的还是旧的？**
缓存 60s TTL 命中时，负载形如：

```json
{"service":"inspector","upstreamStatus":"UP","fetchedAtMs":1795490012734}
```

`fetchedAtMs`（`Long`，epoch millis）是**这条缓存被生成的时刻**。当前 epoch 减它就是本条命中的
年龄——你可以不重探上游、不解析 `PTTL` 直接判断"还能信多久"。

**Q：网关这台机跑的到底是*哪次构建*？**

```text
GET /actuator/info → {"build":{"artifact":"minicc-cloud-gateway","name":"minicc-cloud-gateway",
                            "time":"2026-11-13T04:56:33.309Z","version":"0.1.0","group":"com.minicc.cloud"}}
```

artifact/group/version/time 五键由 `spring-boot-maven-plugin` 的 `build-info` goal 产出，
`META-INF/build-info.properties` 被 Actuator `BuildInfoEndpoint` 自动暴露。测试
`BuildInfoResourceTest` 钉住键集合与格式——build 脚本若停了键校验会红。

## 10. 相关文件

- `minicc-cloud/README.md`
- `minicc-cloud/minicc-cloud-config/src/main/resources/config-repo/application.yml`（共享配置）
- [`docs/SERVICE_PLANE_GATEWAY.md`](SERVICE_PLANE_GATEWAY.md) — 网关三条路由、breaker 参数、暴露的 actuator 端点（本地验证用）
- `docs/SERVICE_PLANE_PLAN.md`（规划）、`docs/SERVICE_PLANE_OPERATOR.md`（本文）
- 合流账本：`docs/ROADMAP_TO_PRODUCT.md`
- 运行/构建 CI：`.github/workflows/ci.yml`
