# minicc-cloud — the service plane around the Python engine

The engine is `minicc` (Python). This directory is the **shell** around it:
service discovery, edge routing, configuration, and a read-only inspector that
calls the Python tools through one bridge. It does not re-implement the engine.

## Modules

| module | port | what it is |
| --- | --- | --- |
| `minicc-cloud-bridge` | — | library: launches/streams the Python tool, applies its budget, redacts stderr |
| `minicc-cloud-registry` | 8761 | Eureka server |
| `minicc-cloud-config` | 8888 | Spring Cloud Config Server (native profile) serving `config-repo/` |
| `minicc-cloud-inspector` | 8081 | read-only workspace change service; refuses paths outside `MINICC_ALLOWEDROOTS` |
| `minicc-cloud-tasks` | 8082 | read-only task history from the Python engine's SQLite store; never writes, never fakes an empty answer |
| `minicc-cloud-insights` | 8087 | read-only aggregate summary (task totals + per-status, audit line count); capped scans, never writes |
| `minicc-cloud-gateway` | 8080 | Spring Cloud Gateway: `lb://` routes, Resilience4j circuit breaker, `/fallback` |

One fact, one home: the gateway's HTTP timeout and the expert circuit breaker's
time limiter both read `minicc.cloud.gateway.response-timeout-seconds`, and the
inspector's Python budget reads `minicc.cloud.inspector.timeout-seconds`. All of
them are served by the config server; the literals in each `application.yml` are
standalone fallbacks, not a second source of truth.

## Run

```bash
cd minicc-cloud
mvn -B test                 # seven modules, no network needed
mvn -DskipTests package
docker compose build
docker compose up
```

```bash
curl localhost:8888/minicc-cloud-gateway/default     # what the config server serves
curl localhost:8080/api/changes?workspace=/workspaces/target
curl localhost:8080/api/insights/summary             # gateway -> insights
```

## Why Java here at all

Because the boundary is worth having: the Python engine stays the only thing
that can write, and the service plane is the only thing that can be scaled or
put behind a gateway. The bridge is the single seam between the two, so a
missing permission, a timeout, or a redacted stderr line has exactly one place
to be fixed.

The plan is in [`../docs/SERVICE_PLANE_PLAN.md`](../docs/SERVICE_PLANE_PLAN.md).
