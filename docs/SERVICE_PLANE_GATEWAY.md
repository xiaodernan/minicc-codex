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

> 一并修掉的历史缺陷：`application.yml` 曾有两个顶层 `spring:` 块，SnakeYAML 直接报 `found duplicate key spring`，网关**上下文根本加载不了**（17 个测试全红）；现合并为单一 `spring:` 树，3 条路由 + redis/cache/rabbitmq 全在同一键下。全 8 模块 `mvn -o clean test` 空环境 93→101 测试全绿。

## 7. 相关位置

- 本文件的 `application.yml`：`minicc-cloud/minicc-cloud-gateway/src/main/resources/application.yml`；
- 共享键的事实家在 Config Server 原生仓：`minicc-cloud/minicc-cloud-config/src/main/resources/config-repo/minicc-cloud-gateway.yml`；
- 规划层入口：`docs/SERVICE_PLANE_PLAN.md`；
- 运维层入口：`docs/SERVICE_PLANE_OPERATOR.md`；
- 故障处理五条：见 `docs/OPERATIONS.md` §6 "doctor 不是什么" —— 本身不能修复，诊断只报不修。
