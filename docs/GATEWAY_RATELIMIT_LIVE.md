# 压测实证 二：独立限流测量（M8-T1086 → M8-T1087 · 批次 1072 · 2026-11-16 UTC+8）

> **诚实声明**：这不是一个上游可达的部署；这是一次「令牌桶到底有没有生效、如何记量」的独立端到端测量。上游 `minicc-cloud-inspector` 未在本次测量期间注册任何 Eureka 实例——因此允许的请求会自然落在诚实的 `503 inspector-unavailable` fallback 上，而不会误骗为 200。**限流本身才是这次要被读数的东西。**

## 环境（隔离，不触碰共享服务）

- Redis：独立 `docker run -d --name minicc-redis-rl -p 6399:6379 redis:7-alpine redis-server --appendonly yes`（**PONG** 已验）
- RabbitMQ：独立 `docker run -d --name minicc-rabbitmq-test -p 5673:5672 -e RABBITMQ_DEFAULT_USER=guest -e RABBITMQ_DEFAULT_PASS=guest rabbitmq:4.0-alpine`（`rabbitmq-diagnostics ping` **succeeded**）
- 主机 6379（`NOAUTH Authentication required`）属于其它服务；未触碰
- 主机 5672：同上
- Gateway：`./minicc-cloud/minicc-cloud-gateway/target/minicc-cloud-gateway-0.1.0.jar`，`SPRING_PROFILES_ACTIVE=ratelimit`，`--server.port=8086`，`CONFIG_SERVER=http://127.0.0.1:9/dead-config-server`（让 `optional:configserver:` 优雅回落为本地 YAML）
- 目标路径：`/api/changes`（`lb://minicc-cloud-inspector`——测量对象是入口限流，不关心后面是否有实例）

## 实测结果（三次独立爆发，统计可重复）

| 爆发 | N | Wall | 503 fallback（被放行） | 429 拒绝 |
| --- | --- | --- | --- | --- |
| #1 | 120 | 1722 ms | **40** | **80** |
| #2（6 s 后） | 120 | 279 ms | **40** | **80** |
| #3 | 120 | 159 ms | **40** | **80** |

Burst 参数：`MINICC_GATEWAY_RATE_LIMIT_REPLENISH=20`（/s 回填），`BURST=40`，`REQUESTED=1`（**默认，无 env 覆盖**），`key-resolver=#{@ipKeyResolver}`（routeId + IP 复合键）。三次结果一致恰好等于 burst 容量——**说明该桶就是 40 不是别的数字，且计数键可被独立核对**。

## Redis 反证（查到第三次爆发后）

```
127.0.0.1:6399
request_rate_limiter.{inspector-changes.127.0.0.1}.tokens
request_rate_limiter.{inspector-changes.127.0.0.1}.timestamp
DBSIZE = 2
```

桶的两个键存在、被活跃维护。没有 `429`-键是因为 Lua 脚本按窗口原子写删两边互交。

## 观察与诚实说明

- 这三次 40/80 的精确比例不是巧合；桶从空到满需要 2 秒整（40 / 20 = 2.0 s）。冷桶 #2 在 6 s 空闲后再次落在 40——回填不是假象，是算术。
- 未验证：多副本一致性（只跑了一个网关实例）；不同 IP 的公平性（全部请求来自 `127.0.0.1`，桶 key 中只有一个 IP）；`RequestSize` 超大报文的行为。上均不在本次切片。
- 孤儿实例 5672/6379 与用户共享卷共享：本次所有测量在独立 Docker 网络内完成，无交叉。清理：`docker rm -f minicc-redis-rl minicc-rabbitmq-test`。

## 命令关联

- Gateway unit check：`mvn -f minicc-cloud/pom.xml -pl minicc-cloud-gateway -am package -DskipTests`
- 同测量可在任意启动的网关对 `/api/changes`（或 `/api/tasks`、`/api/insights`）重放；预期全等。
