# minicc-cloud 网关：路由、熔断与管理面

本文档档案记录网关的**实际配置**（不是规划；所有数值均取自本仓 `minicc-cloud/minicc-cloud-gateway/src/main/resources/application.yml`），供运维参考。

## 1. 端口与占位

- 端口 `8080`；服务名 `minicc-cloud-gateway`；
- Eureka: `${EUREKA_ZONE:http://localhost:8761/eureka/}`（CI / 本机测试可关闭注册 Discovery client，网关仍可启动）；
- Config server: `${CONFIG_SERVER:http://localhost:8888}`，`optional:configserver:`——未拉起 config server 时使用本文件底部的值作为独立 fallback，不是第二事实家。

## 2. 路由（三条）

| id | uri | predicates | filters |
| --- | --- | --- | --- |
| `inspector-changes` | `lb://minicc-cloud-inspector` | `Path=/api/changes,/api/changes/**` | RequestSize(`minicc.cloud.gateway.max-request-bytes:1048576`)、CircuitBreaker(`inspector-route`, fallback `/fallback/inspector`) |
| `tasks` | `lb://minicc-cloud-tasks` | `Path=/api/tasks,/api/tasks/**` | RequestSize(`minicc.cloud.gateway.max-request-bytes:1048576`)、CircuitBreaker(`tasks-route`, fallback `/fallback/inspector`) |
| `insights` | `lb://minicc-cloud-insights` | `Path=/api/insights,/api/insights/**` | RequestSize(`minicc.cloud.gateway.max-request-bytes:1048576`)、CircuitBreaker(`insights-route`, fallback `/fallback/insights`) |

**没有 `/api/doctor`、`/api/capabilities`、`/api/models`** ——网关只代理三个后端，不直接转发给 Python；要拿诊断请直连 `minicc-web`（`/api/doctor`）。`/fallback/insights` 与 `/fallback/inspector` 都返回 503 + `{"error": …, "reason": …}`，绝不把"洞察服务/摘要不可用"伪装成 200 空数据。

## 3. Resilience4j

三条 circuit breaker 参数相同，只是名字不同（`inspector-route`、`tasks-route`、`insights-route`）：

- `sliding-window-size: 10`, `failure-rate-threshold: 50`(%)，
- `wait-duration-in-open-state: 10s`，
- `permitted-number-of-calls-in-half-open-state: 2`，
- `register-health-indicator: true` —— 暴露给 Actuator health。

`timelimiter` 对三条 route 都是 `${minicc.cloud.gateway.response-timeout-seconds:40}s`，`cancel-running-future: true`。

## 4. 管理面端点

`management.endpoints.web.exposure.include`：`health,info,metrics,gateway,circuitbreakers,circuitbreakerevents`。

- `GET/actuator/gateway/routes` 列出定义中的三条路由；
- `GET/actuator/circuitbreakers` 和 `/circuitbreakerevents` 给出三条 breaker 状态；
- `GET/actuator/health` 是 liveness；`show-details: when-authorized`——只在带 bearer token 时给详情。

## 5. 不要做的事

- 不要把 Python `AgentService` 的 `--doctor`/`--setup`/`--stats` 通过网关暴露成 `/gateway/api/doctor`；它们是 CLI 旗标，语义与 CLI 命令绑定的认证边界不同。
- 超过 `max-request-bytes` 的请求在被 circuit breaker 计数**之前**被拒（RequestSize 先于 CircuitBreaker），一帧 client 不会撑熔整条路由。

## 6. 缓存键与失效总线（M8-T826）

网关把 inspector/insights 的读结果缓存在 Redis（`cache-names: gateway-routes`，TTL 60s）。三处必须说同一个键名，否则失效会**静默失手**：控制器 `@Cacheable` 写入、下游发布失效消息、监听器 evict。

- **键的唯一家** `minicc-cloud-gateway/.../CacheKeys.java`：`INSPECTOR_STATUS="inspector:status"`、`INSIGHTS_SUMMARY="insights:summary"`；`forService("inspector")` 与 `forService("inspector:status")` 都解析到同一个规范键，未知服务返回 `null`（一个拼错的名字不许清掉别的服务）。控制器与监听器都问它，字面量不再各存一份。
- **发布端** `CacheInvalidationPublisher.invalidate(service)`：只接受已知服务，发「服务名 payload + `route` header = 规范键」的消息。
- **fanout 交换**：消息发到 `minicc.gateway.route.refresh`（fanout），绑定 `minicc.gateway.cache.invalidate` 队列。生产有多个网关副本，若直接按队列名 publish，只有抢到的那个副本 evict、其余仍读 stale；fanout 让**每个副本**都失效。`RabbitMqConfig` 声明 exchange + binding，不再是孤立常量。
- **离线可测**：`src/test/resources/application.properties` 用不同扩展名覆盖 `spring.rabbitmq.listener.simple.auto-startup=false` 等（同名 `application.yml` 会遮蔽掉主配置的 3 条路由，故不用）；生产默认仍连 broker。`ShippedCacheKeysAgreeTest`（8 条）用 mock 钉住「写入键 = 发布键 = evict 键」与 fanout 拓扑，`ShippedYamlHasOneSpringTreeTest`（2 条）钉住 YAML 无重复顶层键。
- **缓存的值不再模拟（M8-T848 → M8-T861）**：`CachedRouteController` 原来只 `Map.of(...)` 写死 `cached: true`，60s TTL 本质是"过期后重新拿一个同样的常量"。M8-T848 改为 `UpstreamHealthProbe`（`HttpUpstreamHealthProbe`）用 **client-side LB** 解 `lb://<service>/actuator/health` 的真实状态码，但 @Cacheable 就挂在控制器上、缓存 `Mono<ResponseEntity<Map>>`——**`ResponseEntity` 不实现 `Serializable`**，真实 Redis 的 JDK 序列化器写不进去（单测全是 `spring.cache.type=none`，从没人看见）。M8-T861 修法：新增 `CachedStatusService` 作 @Cacheable 边界——缓存的是 **纯 Map / String**（JDK 可序列化），控制器只负责 `ResponseEntity` 包装；`CachedPayloadRoundTripTest` 用真序列化器把 payload 对写/读；`ShippedCacheKeysAgreeTest` 改对 Service 源码取证。**实机（2026-11-13）**：registry + inspector（`.venv` 解释器） + 一次性 Redis 7 跑通——首个 `/api/cached/inspector/status` 后 Redis 出现 `gateway-routes::inspector:status`（TTL 60s），第二次 74ms vs 首次 2199ms（缓存命中）；`/api/cached/inspector/changes?workspace=<abs>` 首调 4.7s（lb:// → inspector → Python bridge），二调 64ms。
- **新增 `/api/cached/inspector/changes?workspace=<abs>`（M8-T861）**：`InspectorChangesProbe`（接口） + `HttpInspectorChangesProbe`（`lb://minicc-cloud-inspector/api/changes`，问号编码由 WebClient 处理，35s 上限—对齐 inspector Python 子进程 30s 预算）。body 是原始 JSON String，按 `inspector:changes:<workspace>` 进 Redis（60s TTL 上限）；**eviction bus 只驱逐 `inspector:status` 与 `insights:summary`**（按服务名定向），changes 键只随 TTL 过期——这是刻意取舍，不是遗漏。
- **inspector 独立启动修复（M8-T861）**：`MiniccProperties` 有两个构造器（compact 全参 + 4 参便捷式），`@ConfigurationPropertiesScan` 找不到缺省构造器 → 上下文加载直接失败（该模块此前**从未独立 boot 过**）；compact 构造器标注 `@ConstructorBinding` 后独立启动正常。
- **注**：`/api/cached/inspector/changes` 的响应体可能包含工作区内变更清单——只对本机信任边界内暴露；若部署到非回环，需要适配网关的认证（同 `/fallback` 语义）。
- **聚合健康面 `/api/health/all`（M8-T850）**：`AggregateHealthController` 用 **同一个** `UpstreamHealthProbe`，对 `minicc-cloud-inspector` / `minicc-cloud-tasks` / `minicc-cloud-insights` 三个服务**并行**（WebFlux `Flux`）探活，产出 `{"services":[...], "upCount":N, "totalServices":3}`——运维一个 endpoint 看全三个后端的 `lb://` 健康；一个服务显示 DOWN，谁知道分也算得到。`AggregateHealthControllerTest`（3 条）钉住"all-up=3 / 一坏+一 unknown=1 / all-down=0"。
- **探活 bounded timeout（M8-T860）**：`HttpUpstreamHealthProbe` 的每个上游探活有硬上限——默认 **2s**（`minicc.cloud.gateway.probe-timeout-ms`，环境变量 `MINICC_GATEWAY_PROBE_TIMEOUT_MS` 覆盖），`.timeout()` 之后接 `onErrorReturn(UNKNOWN)`；一个卡死的上游不会拖住聚合答案。`ProbeTimeoutTest`（3 条）钉住「永不返回的上游在窗口内 resolve 为 UNKNOWN」。
- **Spring Cloud LoadBalancer health check（M8-T871）**：`spring.cloud.loadbalancer.health-check.path.default=/actuator/health` + `interval=10s` ——Eureka 注册表的 UP tag 只能停在「上一次心跳成功」上；真正的 `/actuator/health` 才是当前状态。LB 现在每 10 秒直接打每个候选实例，一旦 /health 失败就过滤出服务列表——不等 Eureka 续约（默认 30s），也不等 60s Caffeine 缓存刷新。实测（2026-11-13，compose 全栈）：tasks/inspector/insights 全部 3/3 UP、`/actuator/health` UP、cached routes roundtrip 正常（Redis `gateway-routes::inspector:status` + `gateway-routes::insights:summary` 写入；删除实例也被 LB 自动剔除——health check 过滤掉死实例后的下一次 poll/answer 仍然活下来）。


> 一并修掉的历史缺陷：`application.yml` 曾有两个顶层 `spring:` 块，SnakeYAML 直接报 `found duplicate key spring`，网关**上下文根本加载不了**（17 个测试全红）；现合并为单一 `spring:` 树，3 条路由 + redis/cache/rabbitmq 全在同一键下。全 8 模块 `mvn -o clean test` 空环境 93→101 测试全绿。

## 7. 相关位置

- 本文件的 `application.yml`：`minicc-cloud/minicc-cloud-gateway/src/main/resources/application.yml`；
- 共享键的事实家在 Config Server 原生仓：`minicc-cloud/minicc-cloud-config/src/main/resources/config-repo/minicc-cloud-gateway.yml`；
- 规划层入口：`docs/SERVICE_PLANE_PLAN.md`；
- 运维层入口：`docs/SERVICE_PLANE_OPERATOR.md`；
- 故障处理五条：见 `docs/OPERATIONS.md` §6 "doctor 不是什么" —— 本身不能修复，诊断只报不修。
