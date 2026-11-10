# minicc-cloud 网关：路由、熔断与管理面

本文档档案记录网关的**实际配置**（不是规划；所有数值均取自本仓 `minicc-cloud/minicc-cloud-gateway/src/main/resources/application.yml`），供运维参考。

## 1. 端口与占位

- 端口 `8080`；服务名 `minicc-cloud-gateway`；
- Eureka: `${EUREKA_ZONE:http://localhost:8761/eureka/}`（CI / 本机测试可关闭注册 Discovery client，网关仍可启动）；
- Config server: `${CONFIG_SERVER:http://localhost:8888}`，`optional:configserver:`——未拉起 config server 时使用本文件底部的值作为独立 fallback，不是第二事实家。

## 2. 路由（两条）

| id | uri | predicates | filters |
| --- | --- | --- | --- |
| `inspector-changes` | `lb://minicc-cloud-inspector` | `Path=/api/changes,/api/changes/**` | RequestSize(`minicc.cloud.gateway.max-request-bytes:1048576`)、CircuitBreaker(`inspector-route`, fallback `/fallback/inspector`) |
| `tasks` | `lb://minicc-cloud-tasks` | `Path=/api/tasks,/api/tasks/**` | RequestSize(`minicc.cloud.gateway.max-request-bytes:1048576`)、CircuitBreaker(`tasks-route`, fallback `/fallback/inspector`) |

**没有 `/api/doctor`、`/api/capabilities`、`/api/models`** ——网关只代理两个后端，不直接转发给 Python；要拿诊断请直连 `minicc-web`（`/api/doctor`）。

## 3. Resilience4j

两条 circuit breaker 参数相同，只是名字不同：

- `sliding-window-size: 10`, `failure-rate-threshold: 50`(%)，
- `wait-duration-in-open-state: 10s`，
- `permitted-number-of-calls-in-half-open-state: 2`，
- `register-health-indicator: true` —— 暴露给 Actuator health。

`timelimiter` 对两条 route 都是 `${minicc.cloud.gateway.response-timeout-seconds:40}s`，`cancel-running-future: true`。

## 4. 管理面端点

`management.endpoints.web.exposure.include`：`health,info,metrics,gateway,circuitbreakers,circuitbreakerevents`。

- `GET/actuator/gateway/routes` 列出定义中的两条路由；
- `GET/actuator/circuitbreakers` 和 `/circuitbreakerevents` 给出两条 breaker 状态；
- `GET/actuator/health` 是 liveness；`show-details: when-authorized`——只在带 bearer token 时给详情。

## 5. 不要做的事

- 不要把 Python `AgentService` 的 `--doctor`/`--setup`/`--stats` 通过网关暴露成 `/gateway/api/doctor`；它们是 CLI 旗标，语义与 CLI 命令绑定的认证边界不同。
- 超过 `max-request-bytes` 的请求在被 circuit breaker 计数**之前**被拒（RequestSize 先于 CircuitBreaker），一帧 client 不会撑熔整条路由。

## 6. 相关位置

- 本文件的 `application.yml`：`minicc-cloud/minicc-cloud-gateway/src/main/resources/application.yml`；
- 共享键的事实家在 Config Server 原生仓：`minicc-cloud/minicc-cloud-config/src/main/resources/config-repo/minicc-cloud-gateway.yml`；
- 规划层入口：`docs/SERVICE_PLANE_PLAN.md`；
- 运维层入口：`docs/SERVICE_PLANE_OPERATOR.md`；
- 故障处理五条：见 `docs/OPERATIONS.md` §6 "doctor 不是什么" —— 本身不能修复，诊断只报不修。
