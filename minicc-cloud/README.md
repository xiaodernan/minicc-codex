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
| `minicc-cloud-insights` | 8087 | read-only aggregate summary (task totals + per-status, audit line count) + fleet topology from the registry (`/api/insights/fleet`: service inventory, instance counts, real UP/DOWN); capped scans, never writes |
| `minicc-cloud-gateway` | 8080 | Spring Cloud Gateway: `lb://` routes, Resilience4j circuit breaker, `/fallback` |

One fact, one home: the gateway's HTTP timeout and the expert circuit breaker's
time limiter both read `minicc.cloud.gateway.response-timeout-seconds`, and the
inspector's Python budget reads `minicc.cloud.inspector.timeout-seconds`. All of
them are served by the config server; the literals in each `application.yml` are
standalone fallbacks, not a second source of truth.

## Run

```bash
cd minicc-cloud
mvn -B test                 # eight modules, no network needed
mvn -DskipTests package
docker compose build
docker compose up
```

```bash
curl localhost:8888/minicc-cloud-gateway/default     # what the config server serves
curl localhost:8080/api/changes?workspace=/workspaces/target
curl localhost:8080/api/insights/summary             # gateway -> insights (task + audit totals)
curl localhost:8080/api/insights/fleet               # gateway -> insights -> Eureka registry (service topology)
curl localhost:8088/api/evidence?latest=1             # the freshest captured CI run (or an honest present:false)
curl localhost:8088/api/evidence?run_id=44225251410   # one run; backfill once from GitHub, then cached
```

## Why Java here at all

Because the boundary is worth having: the Python engine stays the only thing
that can write, and the service plane is the only thing that can be scaled or
put behind a gateway. The bridge is the single seam between the two, so a
missing permission, a timeout, or a redacted stderr line has exactly one place
to be fixed.

The plan is in [`../docs/SERVICE_PLANE_PLAN.md`](../docs/SERVICE_PLANE_PLAN.md).

## Verified end-to-end (2026-11-19, Windows, Temurin JDK 25.0.1)

The plane is not just built — it runs. The proof, recorded so it can be
re-run without guessing:

```powershell
# jars already built by `mvn -B -DskipTests package`
$work = "$env:TEMP\minicc-cloud-smoke"          # ASCII workdir: the real path
Copy-Item minicc-cloud-*\target\*.jar $work     # is full of CJK, which
                                                # breaks `-jar` with spaces

# 1. Eureka registry (port 19500)
java -jar $work\minicc-cloud-registry.jar --server.port=19500

# 2. Inspector (port 19592) — the bridge needs a REAL python, and cwd = repo
#    root so `from minicc.changes import ChangeInspector` resolves
java -jar $work\minicc-cloud-inspector.jar `
  --server.port=19592 `
  --eureka.client.serviceUrl.defaultZone=http://127.0.0.1:19500/eureka/ `
  --minicc.python="C:\Users\<you>\AppData\Local\Python\bin\python.exe"

# 3. Gateway (port 19080)
java -jar $work\minicc-cloud-gateway.jar `
  --server.port=19080 `
  --eureka.client.serviceUrl.defaultZone=http://127.0.0.1:19500/eureka/ `
  --spring.data.redis.host=127.0.0.1 --spring.data.redis.port=26379 `
  --management.health.rabbit.enabled=false
```

Observed:

- Eureka `UP` at ~500ms; inspector registered in ~40s (Eureka renewal window).
- `GET 127.0.0.1:19592/api/changes?workspace=D:\minicc-smoke` → **200**
  (same body through `127.0.0.1:19080/api/changes` → **200** — full chain:
  gateway → Eureka discovery → inspector → Python bridge → live audit data).
- Gateway `/actuator/health` → **200** (with the RabbitMQ health indicator
  disabled; see below).

Three environment traps this run exposed, in order of how long they cost:

1. **`localhost` resolves as `localhost/<unresolved>` inside the JDK here.**
   Pin `--spring.data.redis.host=127.0.0.1` (and prefer `127.0.0.1` in every
   flag) or Lettuce fails with `RedisConnectionException` even though
   `Test-NetConnection 127.0.0.1 26379` says the port is fine.
2. **A down RabbitMQ broker flips actuator health to 503.** For a standalone
   laptop run pass `--management.health.rabbit.enabled=false`. In the full
   `docker compose` deployment the broker exists and the indicator stays on.
3. **The `minicc.python` default is bare `python`,** which does not exist on
   this machine. Pass the absolute interpreter path; the bridge deliberately
   has no silent fallback — it reports `BridgeUnavailableException` instead of
   inventing an empty change set.

Port choices above avoid clashing with the Docker Desktop containers already
listening on 26379 (Redis) and 18081/18888/19883 (crossrealm game/ai/config).
The Eureka instance ID registered as `host.docker.internal:…` because
`hosts` maps that name to this machine's LAN address; that resolves fine
here, but inside compose use `prefer-ip-address: true` (already set).
